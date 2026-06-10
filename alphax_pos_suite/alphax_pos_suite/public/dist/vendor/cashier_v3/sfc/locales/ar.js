/*
 * Arabic locale strings for AlphaX POS v3.
 *
 * Mirror of en.js. Cashiers can switch locale at runtime.
 */

export default {
    app: {
        title: 'نقطة بيع AlphaX',
        loading: 'جاري التحميل...',
        ready: 'جاهز',
        error_generic: 'لم يسر شيء كما هو متوقع.',
        retry: 'حاول مرة أخرى',
        cancel: 'إلغاء',
        ok: 'موافق',
        save: 'حفظ',
        close: 'إغلاق',
        phase2_placeholder_title: 'AlphaX POS v3 — تم تجهيز الأساس',
        phase2_placeholder_body: 'تم تحميل بيئة Vue وتثبيت تطبيق SPA. يجري بناء واجهة الكاشير في المرحلة التالية.',
    },

    boot: {
        warming_up: 'جاري تشغيل نقطة البيع...',
        loading_terminal: 'جاري تحميل إعدادات الجهاز...',
        loading_catalog: 'جاري تحميل الكتالوج...',
        loading_done: 'يكاد ينتهي...',
    },

    station: {
        not_configured: 'الجهاز غير مُهيأ',
        not_configured_body: 'لم يتم ربط هذا الحاسب بجهاز نقطة بيع بعد.',
        ask_manager: 'يجب على المدير إكمال التهيئة لمرة واحدة قبل أن يتمكن هذا الجهاز من تلقي الطلبات.',
    },

    nav: {
        sale: 'بيع',
        return_mode: 'مرتجع',
        holds: 'المحجوزة',
        shift: 'الوردية',
        today: 'اليوم',
        settings: 'الإعدادات',
    },

    cart: {
        title: 'العملية الحالية',
        empty: 'لا توجد منتجات بعد',
        empty_hint: 'امسح باركود أو اختر من القائمة',
        add_customer: 'إضافة عميل',
        subtotal: 'المجموع الفرعي',
        tax: 'الضريبة',
        total: 'الإجمالي',
        hold: 'حجز',
        pay_card: 'الدفع بالبطاقة',
        pay_submit: 'الدفع والإرسال',
    },

    return_mode: {
        banner: 'وضع المرتجع',
        original_label: 'الأصلية',
        exit: 'الخروج من وضع المرتجع',
    },

    catalog: {
        search_placeholder: 'ابحث عن منتج أو امسح باركود...',
        all_items: 'جميع المنتجات',
        ready_to_scan: 'جاهز للمسح',
        no_results: 'لا توجد نتائج',
        loading: 'جاري تحميل الكتالوج...',
    },

    shortcuts: {
        scan: 'مسح',
        customer: 'العميل',
        hold: 'حجز',
        pay: 'دفع',
        return_action: 'مرتجع',
        cancel: 'إلغاء',
    },
};
