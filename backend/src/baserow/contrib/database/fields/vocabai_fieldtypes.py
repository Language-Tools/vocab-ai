from django.db import models
from django.core.exceptions import ValidationError
from baserow.contrib.database.fields.field_cache import FieldCache

from rest_framework import serializers

from baserow.contrib.database.fields.registries import FieldType
from baserow.contrib.database.fields.models import Field
from baserow.contrib.database.views.handler import ViewHandler

from .vocabai_models import TranslationField, LanguageField

from .tasks import run_clt_translation, run_clt_translation_all_rows
from baserow.contrib.database.cloudlanguagetools import instance as clt_instance

import logging
logger = logging.getLogger(__name__)

class LanguageTextField(models.TextField):
    pass

class LanguageFieldType(FieldType):
    type = "language_text"
    model_class = LanguageField
    allowed_fields = ["language"]
    serializer_field_names = ["language"]

    def get_serializer_field(self, instance, **kwargs):
        required = kwargs.get("required", False)
        return serializers.CharField(
            **{
                "required": required,
                "allow_null": not required,
                "allow_blank": not required,
                "default": None,
                **kwargs,
            }
        )

    def get_model_field(self, instance, **kwargs):
        return LanguageTextField(
            default='', blank=True, null=True, **kwargs
        )


class TranslationTextField(models.TextField):
    requires_refresh_after_update = True

class TranslationFieldType(FieldType):
    type = "translation"
    model_class = TranslationField
    allowed_fields = [
        'source_field_id',
        'target_language',
        'service'
    ]
    serializer_field_names = [
        'source_field_id',
        'target_language',
        'service'
    ]
    serializer_field_overrides = {
        "source_field_id": serializers.IntegerField(
            required=False,
            allow_null=True,
            source="source_field.id",
            help_text="The id of the field to translate",
        ),
        "target_language": serializers.CharField(
            required=True,
            allow_null=False,
            allow_blank=False
        ),
        'service': serializers.CharField(
            required=True,
            allow_null=False,
            allow_blank=False
        )
    }

    can_be_primary_field = False

    def prepare_value_for_db(self, instance, value):
        return value

    def get_serializer_field(self, instance, **kwargs):
        return serializers.CharField(
            **{
                "required": False,
                "allow_null": True,
                "allow_blank": True,
                **kwargs,
            }        
        )

    def get_model_field(self, instance, **kwargs):
        return TranslationTextField(
            default=None,
            blank=True, 
            null=True, 
            **kwargs
        )

    def get_field_dependencies(self, field_instance: Field, field_lookup_cache: FieldCache):
        # logger.info(f'get_field_dependencies')
        result = []
        if field_instance.source_field != None:
            result = [field_instance.source_field.name]
        logger.info(f'get_field_dependencies: result {result}')
        return result

    def row_of_dependency_updated(
        self,
        field,
        starting_row,
        update_collector,
        via_path_to_starting_table,
    ):

        if False:
            # when using celery tasks for updates

            logger.info(f'row_of_dependency_updated, row: {starting_row} vars: {vars(starting_row)}, source_field: {vars(field.source_field)}')
            source_internal_field_name = f'field_{field.source_field.id}'
            source_value = getattr(starting_row, source_internal_field_name)

            # add translation logic here:
            # translated_value = 'translation: ' + source_value
            # logger.info(f'starting_row: {starting_row} vars: {vars(starting_row)}')

            table_id = field.table.id
            row_id = starting_row.id
            field_id = f'field_{field.id}'
            run_clt_translation.delay(source_value, table_id, row_id, field_id)

            # update_collector.add_field_with_pending_update_statement(
            #     field,
            #     translated_value,
            #     via_path_to_starting_table=via_path_to_starting_table,
            # )        

        # logging.info(f'field.source_field.language: {field.source_field.language} type: {type(field.source_field.language)}')


        def translate_rows(rows):
            source_language = field.source_field.language  
            target_language = field.target_language
            translation_service = field.service          
            source_internal_field_name = f'field_{field.source_field.id}'
            target_internal_field_name = f'field_{field.id}'
            for row in rows:
                text = getattr(row, source_internal_field_name)
                translated_text = clt_instance.get_translation(text, source_language, target_language, translation_service)
                setattr(row, target_internal_field_name, translated_text)

        update_collector.add_field_with_pending_update_function(
            field,
            update_function=translate_rows,
            via_path_to_starting_table=via_path_to_starting_table,
        )       

        ViewHandler().field_value_updated(field)     

        super().row_of_dependency_updated(
            field,
            starting_row,
            update_collector,
            via_path_to_starting_table,
        )        


    def update_all_rows(self, field):
        logger.info(f'update_all_rows')
        source_field_language = field.source_field.language
        source_field_id = f'field_{field.source_field.id}'
        target_field_id = f'field_{field.id}'

        table_id = field.table.id

        logger.info(f'after_update table_id: {table_id} source_field_id: {source_field_id} target_field_id: {target_field_id}')

        run_clt_translation_all_rows.delay(table_id, source_field_language, source_field_id, target_field_id)

    def after_create(self, field, model, user, connection, before):
        self.update_all_rows(field)

    def after_update(
        self,
        from_field,
        to_field,
        from_model,
        to_model,
        user,
        connection,
        altered_column,
        before,
    ):
        self.update_all_rows(to_field)


