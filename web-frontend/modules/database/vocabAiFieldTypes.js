import { FieldType } from '@baserow/modules/database/fieldTypes'

import GridViewFieldText from '@baserow/modules/database/components/view/grid/fields/GridViewFieldText'
import RowEditFieldText from '@baserow/modules/database/components/row/RowEditFieldText'
import VocabAiTranslationSubForm from '@baserow/modules/database/components/field/VocabAiTranslationSubForm'
import VocabAiTransliterationSubForm from '@baserow/modules/database/components/field/VocabAiTransliterationSubForm'
import VocabAiDictionaryLookupSubForm from '@baserow/modules/database/components/field/VocabAiDictionaryLookupSubForm'
import VocabAiLanguageTextSubForm from '@baserow/modules/database/components/field/VocabAiLanguageTextSubForm'
import FunctionalGridViewFieldText from '@baserow/modules/database/components/view/grid/fields/FunctionalGridViewFieldText'

export class LanguageFieldType extends FieldType {
  static getType() {
    return 'language_text'
  }

  getIconClass() {
    return 'font'
  }

  getName() {
    return 'Language Text'
  }

  getFormComponent() {
    return VocabAiLanguageTextSubForm
  }

  getGridViewFieldComponent() {
    return GridViewFieldText
  }

  getRowEditFieldComponent() {
    return RowEditFieldText
  }

  getFunctionalGridViewFieldComponent() {
    return FunctionalGridViewFieldText
  }

  getDocsDataType(field) {
    return 'string'
  }

  getDocsDescription(field) {
    return this.app.i18n.t('fieldDocs.text')
  }

  getDocsRequestExample(field) {
    return 'string'
  }  

}

export class TranslationFieldType extends FieldType {
  static getType() {
    return 'translation'
  }

  getIconClass() {
    return 'list-ol'
  }

  getName() {
    return 'Translation'
  }

  getFormComponent() {
    return VocabAiTranslationSubForm
  }

  getGridViewFieldComponent() {
    return GridViewFieldText
  }

  getRowEditFieldComponent() {
    return RowEditFieldText
  }

  getFunctionalGridViewFieldComponent() {
    return FunctionalGridViewFieldText
  }

  getDocsDataType(field) {
    return 'string'
  }

  getDocsDescription(field) {
    return this.app.i18n.t('fieldDocs.text')
  }

  getDocsRequestExample(field) {
    return 'string'
  }  

}

export class TransliterationFieldType extends FieldType {
  static getType() {
    return 'transliteration'
  }

  getIconClass() {
    return 'list-ol'
  }

  getName() {
    return 'Transliteration'
  }

  getFormComponent() {
    return VocabAiTransliterationSubForm
  }

  getGridViewFieldComponent() {
    return GridViewFieldText
  }

  getRowEditFieldComponent() {
    return RowEditFieldText
  }

  getFunctionalGridViewFieldComponent() {
    return FunctionalGridViewFieldText
  }

  getDocsDataType(field) {
    return 'string'
  }

  getDocsDescription(field) {
    return this.app.i18n.t('fieldDocs.text')
  }

  getDocsRequestExample(field) {
    return 'string'
  }  

}

export class DictionaryLookupFieldType extends FieldType {
  static getType() {
    return 'dictionary_lookup'
  }

  getIconClass() {
    return 'list-ol'
  }

  getName() {
    return 'Dictionary Lookup'
  }

  getFormComponent() {
    return VocabAiDictionaryLookupSubForm
  }

  getGridViewFieldComponent() {
    return GridViewFieldText
  }

  getRowEditFieldComponent() {
    return RowEditFieldText
  }

  getFunctionalGridViewFieldComponent() {
    return FunctionalGridViewFieldText
  }

  getDocsDataType(field) {
    return 'string'
  }

  getDocsDescription(field) {
    return this.app.i18n.t('fieldDocs.text')
  }

  getDocsRequestExample(field) {
    return 'string'
  }  

}