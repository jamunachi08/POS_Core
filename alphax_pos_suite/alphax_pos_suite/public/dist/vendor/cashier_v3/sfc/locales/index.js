/*
 * Locale bundle entry point.
 *
 * vue-i18n's createI18n() expects `messages: { en: {...}, ar: {...} }`.
 * This module gathers the per-language files and exports the unified
 * structure.
 *
 * Adding a new language: import a new locale file and register it here.
 */

import en from './en.js';
import ar from './ar.js';

export default {
    en,
    ar,
};
