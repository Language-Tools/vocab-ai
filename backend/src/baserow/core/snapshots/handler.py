import datetime
from django.db import IntegrityError
from django.db.models.query import QuerySet
from django.utils import timezone
from django.conf import settings
from baserow.core.models import Group, Snapshot
from baserow.core.models import Application, User
from baserow.core.handler import CoreHandler
from baserow.core.exceptions import (
    ApplicationDoesNotExist,
    ApplicationOperationNotSupported,
)
from baserow.core.snapshots.exceptions import (
    SnapshotDoesNotExist,
    MaximumSnapshotsReached,
    SnapshotIsBeingCreated,
    SnapshotIsBeingRestored,
    SnapshotIsBeingDeleted,
    SnapshotNameNotUnique,
)

from baserow.core.registries import application_type_registry
from baserow.core.signals import application_created
from django.core.files.storage import default_storage
from baserow.core.jobs.models import Job
from baserow.core.jobs.handler import JobHandler
from .job_type import (
    CreateSnapshotJobType,
    RestoreSnapshotJobType,
)
from .tasks import delete_application_snapshot
from baserow.core.utils import Progress


class SnapshotHandler:
    def _count(self, group: Group) -> int:
        """
        Helper method to count the number of snapshots in the provided
        group.

        :param group: The group for which to count the snapshots.
        """

        return Snapshot.objects.filter(
            snapshot_from_application__group=group, mark_for_deletion=False
        ).count()

    def _check_is_in_use(self, snapshot: Snapshot) -> None:
        """
        Checks if the provided snapshot is in use and raises appropriate
        exception if it is.

        :raises SnapshotIsBeingDeleted: When it is not possible to use
            a snapshot as it is being deleted.
        :raises SnapshotIsBeingRestored: When it is not possible to use
            a snapshot as the data are needed to restore it.
        """

        restoring_jobs_count = (
            JobHandler()
            .get_pending_or_running_jobs(RestoreSnapshotJobType.type)
            .filter(snapshot=snapshot)
            .count()
        )

        if restoring_jobs_count > 0:
            raise SnapshotIsBeingRestored()

        if snapshot.mark_for_deletion is True:
            raise SnapshotIsBeingDeleted()

    def list(self, application_id: int, performed_by: User) -> QuerySet:
        """
        Lists all snapshots for the given application id if the provided
        user is in the same group as the application.

        :param application_id: The ID of the application for which to list
            snapshots.
        :param performed_by: The user performing the operation that should
            have sufficient permissions.
        :raises ApplicationDoesNotExist: When the application with the provided id
            does not exist.
        :raises UserNotInGroup: When the user doesn't belong to the same group
            as the application.
        :return: A queryset for snapshots that were created for the given
            application.
        """

        try:
            application = (
                Application.objects.filter(id=application_id)
                .select_related("group")
                .get()
            )
        except Application.DoesNotExist:
            raise ApplicationDoesNotExist(
                f"The application with id {application_id} does not exist."
            )
        application.group.has_user(
            performed_by, raise_error=True, allow_if_template=False
        )

        return (
            Snapshot.objects.filter(
                snapshot_from_application__id=application_id,
                snapshot_to_application__isnull=False,
                mark_for_deletion=False,
            )
            .select_related("created_by")
            .order_by("-created_at")
        )

    def create(self, application_id: int, performed_by: User, name: str):
        """
        Creates a new application snapshot of the given application if the provided
        user is in the same group as the application.

        :param application_id: The ID of the application for which to list
            snapshots.
        :param performed_by: The user performing the operation that should
            have sufficient permissions.
        :param name: The name for the new snapshot.
        :raises ApplicationDoesNotExist: When the application with the provided id
            does not exist.
        :raises UserNotInGroup: When the user doesn't belong to the same group
            as the application.
        :raises MaximumSnapshotsReached: When the group has already reached
            the maximum of allowed snapshots.
        :raises ApplicationOperationNotSupported: When the application type
            doesn't support creating snapshots.
        :raises SnapshotIsBeingCreated: When creating a snapshot is already
            scheduled for the application.
        :raises MaxJobCountExceeded: When the user already has a running
            job to create a snapshot of the same type.
        :return: The snapshot object that was created.
        """

        try:
            application = (
                Application.objects.filter(id=application_id)
                .select_related("group")
                .get()
            )
        except Application.DoesNotExist:
            raise ApplicationDoesNotExist(
                f"The application with id {application_id} does not exist."
            )
        application.group.has_user(
            performed_by, raise_error=True, allow_if_template=False
        )

        app_type = application_type_registry.get_by_model(application.specific_class)
        if app_type.supports_snapshots is False:
            raise ApplicationOperationNotSupported()

        max_snapshots = settings.BASEROW_MAX_SNAPSHOTS_PER_GROUP
        if max_snapshots >= 0 and self._count(application.group) >= max_snapshots:
            raise MaximumSnapshotsReached()

        creating_jobs_count = (
            JobHandler()
            .get_pending_or_running_jobs(CreateSnapshotJobType.type)
            .filter(snapshot__snapshot_from_application=application)
            .count()
        )
        if creating_jobs_count > 0:
            raise SnapshotIsBeingCreated()

        try:
            snapshot = Snapshot.objects.create(
                snapshot_from_application=application,
                created_by=performed_by,
                name=name,
            )
        except IntegrityError as e:
            if "unique constraint" in e.args[0]:
                raise SnapshotNameNotUnique()
            raise e

        job = JobHandler().create_and_start_job(
            performed_by,
            CreateSnapshotJobType.type,
            False,
            snapshot=snapshot,
        )

        return {
            "snapshot": snapshot,
            "job": job,
        }

    def restore(
        self,
        snapshot_id: int,
        performed_by: User,
    ) -> Job:
        """
        Restores a previously created snapshot with the given ID if the
        provided user is in the same group as the application.

        :param snapshot_id: The ID of the snapshot to restore.
        :param performed_by: The user performing the operation that should
            have sufficient permissions.
        :raises SnapshotDoesNotExist: When the snapshot with the provided id
            does not exist.
        :raises UserNotInGroup: When the user doesn't belong to the same group
            as the application.
        :raises ApplicationOperationNotSupported: When the application type
            doesn't support restoring snapshots.
        :raises SnapshotIsBeingDeleted: When it is not possible to use
            a snapshot as it is being deleted.
        :raises SnapshotIsBeingRestored: When it is not possible to use
            a snapshot as the data are needed to restore it.
        :raises MaxJobCountExceeded: When the user already has a running
            job to restore a snapshot of the same type.
        :return: The job that can be used to track the restoring.
        """

        try:
            snapshot = (
                Snapshot.objects.filter(id=snapshot_id)
                .select_for_update(of=("self",))
                .select_related("snapshot_from_application__group")
                .get()
            )
        except Snapshot.DoesNotExist:
            raise SnapshotDoesNotExist()

        group = snapshot.snapshot_from_application.group
        group.has_user(performed_by, raise_error=True, allow_if_template=False)

        app_type = application_type_registry.get_by_model(
            snapshot.snapshot_from_application.specific_class
        )
        if app_type.supports_snapshots is False:
            raise ApplicationOperationNotSupported()

        self._check_is_in_use(snapshot)

        job = JobHandler().create_and_start_job(
            performed_by,
            RestoreSnapshotJobType.type,
            False,
            snapshot=snapshot,
        )

        return job

    def _schedule_deletion(self, snapshot: Snapshot):
        snapshot.mark_for_deletion = True
        snapshot.save()
        delete_application_snapshot.delay(snapshot.snapshot_to_application.id)

    def delete(self, snapshot_id: int, performed_by: User) -> None:
        """
        Deletes a previously created snapshot with the given ID if the
        provided user belongs to the same group as the application.

        :param snapshot_id: The ID of the snapshot to delete.
        :param performed_by: The user performing the operation that should
            have sufficient permissions.
        :raises SnapshotDoesNotExist: When the snapshot with the provided id
            does not exist.
        :raises UserNotInGroup: When the user doesn't belong to the same group
            as the application.
        :raises ApplicationOperationNotSupported: When the application type
            doesn't support deleting snapshots.
        :raises SnapshotIsBeingDeleted: When it is not possible to use
            a snapshot as it is being deleted.
        :raises SnapshotIsBeingRestored: When it is not possible to delete
            a snapshot as the data are needed to restore it.
        :raises MaxJobCountExceeded: When the user already has a running
            job to delete a snapshot of the same type.
        """

        try:
            snapshot = (
                Snapshot.objects.filter(id=snapshot_id)
                .select_for_update(of=("self",))
                .select_related("snapshot_from_application__group")
                .get()
            )
        except Snapshot.DoesNotExist:
            raise SnapshotDoesNotExist()

        group = snapshot.snapshot_from_application.group
        group.has_user(performed_by, raise_error=True, allow_if_template=False)

        app_type = application_type_registry.get_by_model(
            snapshot.snapshot_from_application.specific_class
        )
        if app_type.supports_snapshots is False:
            raise ApplicationOperationNotSupported()

        self._check_is_in_use(snapshot)
        self._schedule_deletion(snapshot)

    def delete_by_application(self, application: Application) -> None:
        """
        Deletes all snapshots related to the provided application.

        :param application: Application for which to delete all related
            snapshots.
        """

        application_snapshots = Snapshot.objects.filter(
            snapshot_from_application=application
        ).select_for_update(of=("self",))
        for snapshot in application_snapshots:
            self._schedule_deletion(snapshot)

    def delete_expired(self) -> None:
        """
        Finds all snapshots that are considered expired based on
        BASEROW_SNAPSHOT_EXPIRATION_TIME_DAYS and schedules their deletion.
        """

        threshold = timezone.now() - datetime.timedelta(
            days=settings.BASEROW_SNAPSHOT_EXPIRATION_TIME_DAYS
        )
        expired_snapshots = Snapshot.objects.filter(
            created_at__lt=threshold
        ).select_for_update(of=("self",))
        for snapshot in expired_snapshots:
            self._schedule_deletion(snapshot)

    def perform_create(self, snapshot: Snapshot, progress: Progress) -> None:
        """
        Creates an actual copy of the original application and stores it as
        another application with its group set to None to effectively hide it
        from the system.

        :raises SnapshotDoesNotExist: When the snapshot with the provided id
            does not exist.
        :raises UserNotInGroup: When the user doesn't belong to the same group
            as the application.
        """

        if snapshot is None:
            raise SnapshotDoesNotExist()

        group = snapshot.snapshot_from_application.group
        group.has_user(snapshot.created_by, raise_error=True, allow_if_template=False)

        application = snapshot.snapshot_from_application.specific
        application_type = application_type_registry.get_by_model(application)
        exported_application = application_type.export_serialized(
            application, None, default_storage
        )
        progress.increment(by=50)
        imported_database = application_type.import_serialized(
            None,
            exported_application,
            {},
            None,
            default_storage,
            progress_builder=progress.create_child_builder(represents_progress=50),
        )
        snapshot.snapshot_to_application = imported_database
        snapshot.save()

    def perform_restore(self, snapshot: Snapshot, progress: Progress) -> Application:
        """
        Creates an application copy from the snapshotted application. The copy
        will be available as a normal application in the same group as the
        original application.

        :raises SnapshotDoesNotExist: When the snapshot with the provided id
            does not exist.
        :raises UserNotInGroup: When the user doesn't belong to the same group
            as the application.
        :returns: Application that is a copy of the snapshot.
        """

        if snapshot is None:
            raise SnapshotDoesNotExist()

        group = snapshot.snapshot_from_application.group
        group.has_user(snapshot.created_by, raise_error=True, allow_if_template=False)

        application = snapshot.snapshot_to_application.specific
        application_type = application_type_registry.get_by_model(application)
        exported_application = application_type.export_serialized(
            application, None, default_storage
        )
        progress.increment(by=50)
        imported_database = application_type.import_serialized(
            snapshot.snapshot_from_application.group,
            exported_application,
            {},
            None,
            default_storage,
            progress_builder=progress.create_child_builder(represents_progress=50),
        )
        imported_database.name = CoreHandler().find_unused_application_name(
            snapshot.snapshot_from_application.group, snapshot.name
        )
        imported_database.save()
        application_created.send(self, application=imported_database, user=None)
        return imported_database
