from django.db import models
from django.core.exceptions import ValidationError
from baserow.contrib.database.fields.field_cache import FieldCache

from rest_framework import serializers

from baserow.contrib.database.fields.registries import FieldType
from baserow.contrib.database.fields.models import Field
from baserow.contrib.database.views.handler import ViewHandler

from .dependencies.models import FieldDependency

from .vocabai_models import TranslationField, TransliterationField, LanguageField, DictionaryLookupField

from .tasks import run_clt_translation_all_rows, run_clt_transliteration_all_rows, run_clt_lookup_all_rows
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


class TransformationFieldType(FieldType):
    def get_field_dependencies(self, field_instance: Field, field_lookup_cache: FieldCache):
        # logger.info(f'get_field_dependencies')
        if field_instance.source_field != None:
            return [
                FieldDependency(
                    dependency=field_instance.source_field,
                    dependant=field_instance
                )
            ]     
        return []    

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

class TranslationFieldType(TransformationFieldType):
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
                if text != None:
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
        target_language = field.target_language
        translation_service = field.service          
        source_field_id = f'field_{field.source_field.id}'
        target_field_id = f'field_{field.id}'

        table_id = field.table.id

        logger.info(f'after_update table_id: {table_id} source_field_id: {source_field_id} target_field_id: {target_field_id}')

        run_clt_translation_all_rows.delay(table_id, 
                                           source_field_language, 
                                           target_language,
                                           translation_service,
                                           source_field_id, 
                                           target_field_id)


class TransliterationFieldType(TransformationFieldType):
    type = "transliteration"
    model_class = TransliterationField
    allowed_fields = [
        'source_field_id',
        'transliteration_id'
    ]
    serializer_field_names = [
        'source_field_id',
        'transliteration_id'
    ]
    serializer_field_overrides = {
        "source_field_id": serializers.IntegerField(
            required=False,
            allow_null=True,
            source="source_field.id",
            help_text="The id of the field to translate",
        ),
        "transliteration_id": serializers.CharField(
            required=True,
            allow_null=False,
            allow_blank=False
        ),
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

    def row_of_dependency_updated(
        self,
        field,
        starting_row,
        update_collector,
        via_path_to_starting_table,
    ):

        def transliterate_rows(rows):
            transliteration_id = field.transliteration_id
            source_internal_field_name = f'field_{field.source_field.id}'
            target_internal_field_name = f'field_{field.id}'
            for row in rows:
                text = getattr(row, source_internal_field_name)
                if text != None:
                    transliterated_text = clt_instance.get_transliteration(text, transliteration_id)
                    setattr(row, target_internal_field_name, transliterated_text)

        update_collector.add_field_with_pending_update_function(
            field,
            update_function=transliterate_rows,
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
        transliteration_id = field.transliteration_id
        source_field_id = f'field_{field.source_field.id}'
        target_field_id = f'field_{field.id}'

        table_id = field.table.id


        run_clt_transliteration_all_rows.delay(table_id, 
                                                transliteration_id,
                                                source_field_id, 
                                                target_field_id)



class DictionaryLookupFieldType(TransformationFieldType):
    type = "dictionary_lookup"
    model_class = DictionaryLookupField
    allowed_fields = [
        'source_field_id',
        'lookup_id'
    ]
    serializer_field_names = [
        'source_field_id',
        'lookup_id'
    ]
    serializer_field_overrides = {
        "source_field_id": serializers.IntegerField(
            required=False,
            allow_null=True,
            source="source_field.id",
            help_text="The id of the field for which to do dictionary lookup",
        ),
        "lookup_id": serializers.CharField(
            required=True,
            allow_null=False,
            allow_blank=False
        ),
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


    def row_of_dependency_updated(
        self,
        field,
        starting_row,
        update_collector,
        via_path_to_starting_table,
    ):

        def perform_dictionary_lookup_rows(rows):
            lookup_id = field.lookup_id
            source_internal_field_name = f'field_{field.source_field.id}'
            target_internal_field_name = f'field_{field.id}'
            for row in rows:
                text = getattr(row, source_internal_field_name)
                if text != None:
                    lookup_result = clt_instance.get_dictionary_lookup(text, lookup_id)
                    setattr(row, target_internal_field_name, lookup_result)

        update_collector.add_field_with_pending_update_function(
            field,
            update_function=perform_dictionary_lookup_rows,
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
        lookup_id = field.lookup_id
        source_field_id = f'field_{field.source_field.id}'
        target_field_id = f'field_{field.id}'

        table_id = field.table.id

        run_clt_lookup_all_rows.delay(table_id, 
                                        lookup_id, 
                                        source_field_id, 
                                        target_field_id)

