import pytest
import datetime
from django.utils import timezone
from freezegun import freeze_time

from baserow.core.models import Snapshot
from baserow.core.snapshots.handler import SnapshotHandler
from baserow.core.utils import Progress
from baserow.test_utils.fixtures import Fixtures

from baserow.contrib.database.table.models import Table


@pytest.mark.django_db
def test_perform_create(data_fixture: Fixtures):
    user, token = data_fixture.create_user_and_token()
    group = data_fixture.create_group(user=user)
    application = data_fixture.create_database_application(group=group, order=1)
    table = data_fixture.create_database_table(user=user, database=application)
    field = data_fixture.create_text_field(user=user, table=table)
    model = table.get_model()
    row_1 = model.objects.create(**{f"field_{field.id}": "Row 1"})
    row_1 = model.objects.create(**{f"field_{field.id}": "Row 2"})
    snapshot = data_fixture.create_snapshot(
        snapshot_from_application=application,
        name="snapshot",
        created_by=user,
    )
    progress = Progress(total=100)

    SnapshotHandler().perform_create(snapshot, progress)

    snapshot.refresh_from_db()
    snapshotted_table = Table.objects.get(database=snapshot.snapshot_to_application)
    model = snapshotted_table.get_model()
    assert model.objects.count() == 2
    assert progress.progress == 100


@pytest.mark.django_db
def test_perform_restore(data_fixture: Fixtures):
    user, token = data_fixture.create_user_and_token()
    group = data_fixture.create_group(user=user)
    application = data_fixture.create_database_application(group=group, order=1)
    application_snapshot = data_fixture.create_database_application(group=None, order=2)
    table = data_fixture.create_database_table(user=user, database=application_snapshot)
    field = data_fixture.create_text_field(user=user, table=table)
    model = table.get_model()
    row_1 = model.objects.create(**{f"field_{field.id}": "Row 1"})
    row_1 = model.objects.create(**{f"field_{field.id}": "Row 2"})
    snapshot = data_fixture.create_snapshot(
        snapshot_from_application=application,
        snapshot_to_application=application_snapshot,
        name="snapshot",
        created_by=user,
    )
    progress = Progress(total=100)

    restored = SnapshotHandler().perform_restore(snapshot, progress)
    restored_table = Table.objects.get(database=restored)
    model = restored_table.get_model()
    assert restored.name == snapshot.name
    assert model.objects.count() == 2
    assert progress.progress == 100


@pytest.mark.django_db
def test_delete_expired_snapshots(data_fixture: Fixtures, settings):
    exp_days = 1
    settings.BASEROW_SNAPSHOT_EXPIRATION_TIME_DAYS = exp_days
    now = timezone.now()
    time_before_expiration = (
        now - datetime.timedelta(days=exp_days) - datetime.timedelta(seconds=10)
    )
    user, token = data_fixture.create_user_and_token()
    group = data_fixture.create_group(user=user)
    application = data_fixture.create_database_application(group=group, order=1)

    with freeze_time(now):
        recent_snapshot = data_fixture.create_snapshot(
            user=user,
            snapshot_from_application=application,
            created_by=user,
            name="recent_snapshot",
        )

    with freeze_time(time_before_expiration):
        expired_snapshot_1 = data_fixture.create_snapshot(
            user=user,
            snapshot_from_application=application,
            created_by=user,
            name="expired_snapshot_1",
        )
        expired_snapshot_2 = data_fixture.create_snapshot(
            user=user,
            snapshot_from_application=application,
            created_by=user,
            name="expired_snapshot_2",
        )

    assert Snapshot.objects.count() == 3

    with freeze_time(now):
        SnapshotHandler().delete_expired()

    assert Snapshot.objects.count() == 1
