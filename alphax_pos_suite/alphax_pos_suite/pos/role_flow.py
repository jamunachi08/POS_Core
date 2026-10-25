"""Role-based process flow: the single source of truth for what each
AlphaX POS role does, in what order, and where it must escalate.

Two consumers:

* ``www/pos_role_flow`` renders it as a page, filtered to the lanes the
  viewer is entitled to see.
* ``get_flow()`` exposes the same filtered payload to the cashier SPA or
  to onboarding, so the help text a user reads can never describe a
  capability that user does not actually hold.

Filtering is done on the server. A lane the viewer may not see is never
serialised into the response, so a cashier cannot read the manager lane
by opening devtools. That is the whole reason this module exists rather
than a static HTML page.

No doctypes, no schema, no migration. Additive only.
"""

from __future__ import annotations

import frappe
from frappe import _

# --------------------------------------------------------------------------
# Role names. Kept as constants so a rename is a one-line change here and
# never a string scattered through templates.
# --------------------------------------------------------------------------

R_CASHIER = "AlphaX POS Cashier"
R_SUPERVISOR = "AlphaX POS Supervisor"
R_MANAGER = "AlphaX POS Manager"
R_KITCHEN = "AlphaX POS Kitchen"
R_ACCOUNTS = "Accounts Manager"
R_ADMIN = "System Manager"

#: Roles that may read every lane, not only their own. Mirrors
#: ``security.manager_pin.MANAGER_ROLES`` \u2014 the tier that can actually
#: authorise a gated action. Supervisor is deliberately NOT here.
SUPERVISORY_ROLES = {R_ADMIN, R_MANAGER}

#: Lanes a role may read in addition to its own, without being a full
#: supervisor. A Supervisor runs the floor and the kitchen pass but holds
#: no PIN, so they read those lanes and not the back office.
EXTRA_LANES = {
    R_SUPERVISOR: ("cashier", "kitchen"),
}

#: Roles that may read the full permission matrix (all columns) even when
#: they only see some lanes. Accounts audits the floor without standing
#: on it; Supervisor needs the grid to know what to escalate.
FULL_MATRIX_ROLES = {R_ADMIN, R_MANAGER, R_SUPERVISOR, R_ACCOUNTS}

#: The documentation-only lanes. Nobody "is" a guest, so the guest lane is
#: shown to supervisors as reference material and to nobody else.
REFERENCE_LANES = {"customer"}


# --------------------------------------------------------------------------
# Lane definitions
# --------------------------------------------------------------------------

LANES = [
    {
        "id": "cashier",
        "role": R_CASHIER,
        "name_en": "Cashier",
        "name_ar": "الكاشير",
        "scope_en": (
            "One bound terminal, one open shift. Sees the cashier screen only "
            "\u2014 no desk, no reports, no totals during a blind close."
        ),
        "scope_ar": (
            "جهاز واحد مرتبط ووردية واحدة مفتوحة. يرى شاشة الكاشير فقط \u2014 دون "
            "لوحة التحكم أو التقارير أو الإجماليات أثناء الإقفال الأعمى."
        ),
        "chips": ["/alphax-pos", "AlphaX POS Shift", "AlphaX POS Terminal", "Sales Invoice"],
        "steps": [
            {
                "t_en": "Log in at the bound terminal",
                "t_ar": "تسجيل الدخول على الجهاز المرتبط",
                "d_en": (
                    "The PC is bound to exactly one AlphaX POS Terminal. An unbound "
                    "or rebound PC cannot open the cashier screen."
                ),
                "d_ar": (
                    "كل جهاز مرتبط بنقطة بيع واحدة فقط. الجهاز غير المرتبط لا يفتح "
                    "شاشة الكاشير."
                ),
                "tag": "block",
                "dt": "AlphaX POS Terminal",
            },
            {
                "t_en": "Shift-in gate",
                "t_ar": "بوابة فتح الوردية",
                "d_en": (
                    "Declare the opening float. Until a shift is open the cart is "
                    "unreachable \u2014 the gate is enforced server-side, not just "
                    "hidden in the UI."
                ),
                "d_ar": (
                    "إدخال الرصيد الافتتاحي. لا يمكن الوصول إلى السلة قبل فتح الوردية "
                    "\u2014 والقيد مُطبّق على الخادم لا في الواجهة فقط."
                ),
                "tag": "block",
                "dt": "AlphaX POS Shift",
            },
            {
                "t_en": "Store hours check",
                "t_ar": "التحقق من ساعات العمل",
                "d_en": (
                    "Outside configured trading hours the terminal refuses to open a "
                    "shift. The scheduler also force-closes a shift left open past "
                    "closing time and flags it RECOUNT REQUIRED."
                ),
                "d_ar": (
                    "خارج ساعات العمل المعتمدة يرفض الجهاز فتح وردية. كما يُقفل المجدول "
                    "أي وردية متروكة بعد موعد الإغلاق ويضع عليها علامة إعادة العد."
                ),
                "tag": "auto",
                "dt": "AlphaX POS Outlet \u00b7 store hours",
            },
            {
                "t_en": "Choose order type",
                "t_ar": "اختيار نوع الطلب",
                "d_en": (
                    "Dine-in, takeaway, delivery or drive-thru. Each order type carries "
                    "its own table policy (Mandatory / Optional / Not Applicable) and "
                    "its own channel price list."
                ),
                "d_ar": (
                    "محلي أو سفري أو توصيل أو خدمة السيارات. لكل نوع سياسة طاولة خاصة "
                    "(إلزامية / اختيارية / غير منطبقة) وقائمة أسعار قناة مستقلة."
                ),
                "dt": "AlphaX POS Order Type",
            },
            {
                "t_en": "Select or create a table",
                "t_ar": "اختيار طاولة أو إنشاؤها",
                "d_en": (
                    "Two-axis state: occupancy \u00d7 readiness. The cashier may create a "
                    "table on the fly. Cover count is captured for turn-time reporting."
                ),
                "d_ar": (
                    "حالة ثنائية المحور: الإشغال \u00d7 الجاهزية. يمكن للكاشير إنشاء طاولة "
                    "فوراً. ويُسجَّل عدد الأفراد لتقارير زمن الدوران."
                ),
                "dt": "AlphaX POS Table",
            },
            {
                "t_en": "Build the cart",
                "t_ar": "بناء السلة",
                "d_en": (
                    "Menu resolved as set algebra over item groups. Fixed combos drop in "
                    "as-is; customisable combos open the ComboPicker for substitutions "
                    "within a group, charging any price difference."
                ),
                "d_ar": (
                    "تُبنى القائمة كعمليات مجموعات على مجموعات الأصناف. العروض الثابتة "
                    "تُضاف كما هي، أما المرنة فتفتح نافذة الاختيار للاستبدال داخل المجموعة "
                    "مع احتساب فرق السعر."
                ),
                "dt": "AlphaX POS Menu \u00b7 Combo Offer",
            },
            {
                "t_en": "Line discount or price override",
                "t_ar": "خصم السطر أو تجاوز السعر",
                "d_en": (
                    "Below the configured threshold the cashier proceeds alone. Above it, "
                    "or for any price override, the manager-PIN dialog opens and the "
                    "attempt is logged either way."
                ),
                "d_ar": (
                    "تحت الحد المعتمد يتابع الكاشير بنفسه. أما فوقه أو عند تجاوز السعر "
                    "فتُفتح نافذة رمز المدير، وتُسجّل المحاولة في كل الأحوال."
                ),
                "tag": "gate",
                "dt": "AlphaX POS Manager Authorization Log",
            },
            {
                "t_en": "Send to kitchen",
                "t_ar": "الإرسال إلى المطبخ",
                "d_en": (
                    "KOT routing rules split the ticket by print station, or merge into "
                    "one printer with section headings in single-printer mode. A KDS "
                    "ticket is pushed over realtime."
                ),
                "d_ar": (
                    "تُوزَّع قسيمة المطبخ حسب محطات الطباعة، أو تُدمج في طابعة واحدة مع "
                    "عناوين أقسام في وضع الطابعة المفردة، وتُرسل التذكرة للشاشة فورياً."
                ),
                "tag": "auto",
                "dt": "Print Station \u00b7 KOT Routing Rule",
            },
            {
                "t_en": "Take payment",
                "t_ar": "استلام الدفع",
                "d_en": (
                    "Cash, card, split tender, or redemption against the customer's store "
                    "credit balance. Inclusive VAT is extracted line by line from the "
                    "displayed price."
                ),
                "d_ar": (
                    "نقداً أو بالبطاقة أو دفع مجزأ أو خصماً من رصيد العميل. وتُستخرج "
                    "الضريبة المشمولة من السعر المعروض سطراً بسطر."
                ),
                "dt": "Mode of Payment \u00b7 Store Credit Ledger",
            },
            {
                "t_en": "Submit the sale",
                "t_ar": "ترحيل البيع",
                "d_en": (
                    "One submit writes the Sales Invoice, the GL entries, the stock ledger "
                    "movement, the tobacco-fee reposting journal where applicable, and "
                    "queues the ZATCA submission."
                ),
                "d_ar": (
                    "ترحيل واحد ينشئ فاتورة المبيعات وقيود الأستاذ وحركة المخزون وقيد "
                    "رسوم التبغ عند انطباقه، ويضع إرسال هيئة الزكاة في قائمة الانتظار."
                ),
                "tag": "post",
                "dt": "Sales Invoice \u00b7 GL Entry \u00b7 Stock Ledger Entry",
            },
            {
                "t_en": "Print and announce",
                "t_ar": "الطباعة والإعلان",
                "d_en": (
                    "AlphaX Thermal 80mm receipt with the ZATCA QR. The customer display "
                    "board announces the order bilingually by voice."
                ),
                "d_ar": (
                    "إيصال حراري ٨٠ مم مع رمز هيئة الزكاة، وتُعلن شاشة العميل الطلب "
                    "صوتياً بالعربية والإنجليزية."
                ),
                "dt": "AlphaX Thermal 80mm",
            },
            {
                "t_en": "Hold, recall, or sync offline",
                "t_ar": "التعليق أو الاسترجاع أو المزامنة",
                "d_en": (
                    "Held orders are recalled by the same cashier. If the link drops, sales "
                    "queue locally and replay with exponential backoff; blocked and "
                    "transient failures are classified separately."
                ),
                "d_ar": (
                    "تُسترجع الطلبات المعلّقة من الكاشير نفسه. وعند انقطاع الاتصال تُخزَّن "
                    "المبيعات محلياً وتُعاد المزامنة تدريجياً، مع الفصل بين الأخطاء المانعة "
                    "والمؤقتة."
                ),
                "dt": "Sync Queue",
            },
            {
                "t_en": "Return or refund",
                "t_ar": "المرتجع أو الاسترداد",
                "d_en": (
                    "Within the policy window and value the cashier completes it alone. "
                    "Older, larger, or credit-note edits escalate to a manager PIN."
                ),
                "d_ar": (
                    "داخل حدود السياسة يتم المرتجع مباشرة، أما الأقدم أو الأكبر أو تعديل "
                    "الإشعار الدائن فيتطلب رمز المدير."
                ),
                "tag": "gate",
                "dt": "Sales Invoice (Return)",
            },
            {
                "t_en": "Blind shift close",
                "t_ar": "الإقفال الأعمى للوردية",
                "d_en": (
                    "The cashier counts and enters cash without ever seeing expected "
                    "totals \u2014 the server strips them from the payload for non-managers. "
                    "Variance beyond tolerance waits on a manager."
                ),
                "d_ar": (
                    "يعدّ الكاشير النقد ويدخله دون رؤية الإجماليات المتوقعة \u2014 إذ يحذفها "
                    "الخادم من البيانات لغير المدراء. وأي فرق يتجاوز الحد ينتظر موافقة المدير."
                ),
                "tag": "gate",
                "dt": "AlphaX POS Shift \u00b7 blind close",
            },
            {
                "t_en": "Or hand over the desk",
                "t_ar": "أو تسليم المركز",
                "d_en": (
                    "A handover closes this cashier's period and opens the next one without "
                    "triggering day close, keeping an unbroken cash chain of custody."
                ),
                "d_ar": (
                    "التسليم يُقفل فترة هذا الكاشير ويفتح التالية دون تفعيل إقفال اليوم، مع "
                    "الحفاظ على تسلسل عهدة النقد."
                ),
                "dt": "AlphaX POS Shift \u00b7 is_handover",
            },
        ],
    },
    {
        "id": "supervisor",
        "role": R_SUPERVISOR,
        "name_en": "Shift Supervisor",
        "name_ar": "مشرف الوردية",
        "scope_en": (
            "Runs the floor and sees what the cashier is blinded from, but holds no "
            "PIN. Every gated action still escalates past this role to a manager."
        ),
        "scope_ar": (
            "يدير الصالة ويرى ما يُحجب عن الكاشير، لكنه لا يحمل رمزاً. وكل إجراء مقيّد "
            "يتجاوز هذا الدور إلى المدير."
        ),
        "chips": ["_is_manager()", "X Report", "open_shift(for_user)", "AlphaX POS Shift"],
        "steps": [
            {
                "t_en": "Cover the floor",
                "t_ar": "تغطية الصالة",
                "d_en": (
                    "A supervisor may ring up sales exactly like a cashier \u2014 the posting "
                    "guard admits Cashier, Supervisor, Manager and System Manager alike."
                ),
                "d_ar": (
                    "يمكن للمشرف تنفيذ المبيعات كالكاشير تماماً، إذ يسمح حارس الترحيل "
                    "للكاشير والمشرف والمدير ومسؤول النظام على حد سواء."
                ),
                "dt": "pos/posting.py \u00b7 _ensure_role_allowed",
            },
            {
                "t_en": "Open a shift on behalf of a cashier",
                "t_ar": "فتح وردية نيابة عن كاشير",
                "d_en": (
                    "Where a cashier cannot reach the desk, the supervisor opens the shift "
                    "for them. The shift owner becomes the cashier; the audit trail still "
                    "records who actually performed it."
                ),
                "d_ar": (
                    "عند تعذّر وصول الكاشير، يفتح المشرف الوردية نيابة عنه. فيصبح الكاشير "
                    "مالك الوردية، ويبقى سجل التدقيق مسجلاً من نفّذ الإجراء فعلياً."
                ),
                "dt": "open_shift(for_user=\u2026)",
            },
            {
                "t_en": "See unblinded shift totals",
                "t_ar": "رؤية إجماليات الوردية غير المحجوبة",
                "d_en": (
                    "The blind-close stripper admits this role, so the supervisor reads the "
                    "live X report and the expected-cash figure the cashier never sees."
                ),
                "d_ar": (
                    "يسمح مُخفي الإقفال الأعمى لهذا الدور، فيقرأ المشرف تقرير X المباشر "
                    "ورقم النقد المتوقع الذي لا يراه الكاشير."
                ),
                "dt": "shift_api.py \u00b7 _MANAGER_ROLES",
            },
            {
                "t_en": "Review the close and the variance",
                "t_ar": "مراجعة الإقفال والفرق",
                "d_en": (
                    "Recount with the cashier, accept the count, and close or reopen the "
                    "shift. Day close and handover both sit inside this role."
                ),
                "d_ar": (
                    "إعادة العد مع الكاشير واعتماد النتيجة ثم الإقفال أو إعادة الفتح، ويشمل "
                    "الدور إقفال اليوم والتسليم."
                ),
                "dt": "AlphaX POS Shift \u00b7 variance",
            },
            {
                "t_en": "Escalate anything PIN-gated",
                "t_ar": "تصعيد كل ما يتطلب رمزاً",
                "d_en": (
                    "This is the boundary: PIN authorisation is restricted to Manager and "
                    "System Manager, so a supervisor facing an over-threshold discount, a "
                    "price override or a terminal rebind still fetches a manager."
                ),
                "d_ar": (
                    "هنا الحد الفاصل: التفويض بالرمز مقصور على المدير ومسؤول النظام، فالمشرف "
                    "أمام خصم يتجاوز الحد أو تجاوز سعر أو إعادة ربط جهاز يستدعي مديراً."
                ),
                "tag": "gate",
                "dt": "security/manager_pin.py \u00b7 MANAGER_ROLES",
            },
            {
                "t_en": "Cannot approve a flagged order",
                "t_ar": "لا يعتمد الطلبات الموقوفة",
                "d_en": (
                    "An order that trips the approval rule can only be set Approved by a "
                    "Manager or System Manager. For everyone else it parks as Pending."
                ),
                "d_ar": (
                    "الطلب الذي تُفعّل عليه قاعدة الاعتماد لا يعتمده إلا المدير أو مسؤول "
                    "النظام، ويبقى لغيرهما في حالة انتظار."
                ),
                "tag": "block",
                "dt": "pos/posting.py \u00b7 approval_status",
            },
        ],
    },
    {
        "id": "manager",
        "role": R_MANAGER,
        "name_en": "Store Manager",
        "name_ar": "مدير الفرع",
        "scope_en": (
            "Authorises what the cashier cannot, holds the PIN, owns the cash chain "
            "and the trading day. Sees totals the cashier never sees."
        ),
        "scope_ar": (
            "يفوّض ما لا يملكه الكاشير، ويحتفظ بالرمز، ويتحمل مسؤولية عهدة النقد واليوم "
            "التجاري. ويرى إجماليات لا يراها الكاشير."
        ),
        "chips": ["AlphaX POS Manager PIN", "Authorization Log", "Day Close", "Shift Register"],
        "steps": [
            {
                "t_en": "Hold a manager PIN",
                "t_ar": "الاحتفاظ برمز المدير",
                "d_en": (
                    "Stored as a bcrypt hash, never in clear text. Creation, reset and "
                    "deletion all write to the authorisation log even when the PIN record "
                    "itself is gone."
                ),
                "d_ar": (
                    "يُخزَّن مشفّراً بخوارزمية bcrypt ولا يُحفظ نصاً صريحاً. ويُسجَّل إنشاؤه "
                    "وإعادة ضبطه وحذفه في سجل التفويض حتى بعد حذف السجل نفسه."
                ),
                "dt": "AlphaX POS Manager PIN",
            },
            {
                "t_en": "Bind and rebind terminals",
                "t_ar": "ربط الأجهزة وإعادة ربطها",
                "d_en": (
                    "A new cashier PC is tied to a terminal after PIN verification. "
                    "Rebinding an existing PC is the same gate \u2014 no silent reassignment."
                ),
                "d_ar": (
                    "يُربط أي جهاز جديد بنقطة بيع بعد التحقق من الرمز، وإعادة الربط تخضع "
                    "للبوابة نفسها دون أي نقل صامت."
                ),
                "tag": "gate",
                "dt": "AlphaX POS Terminal",
            },
            {
                "t_en": "Authorise at the cashier's station",
                "t_ar": "التفويض من جهاز الكاشير",
                "d_en": (
                    "Discount above threshold, price override, out-of-policy return, void "
                    "or cancel. The manager walks over and types the PIN; user, terminal, "
                    "action and time are recorded."
                ),
                "d_ar": (
                    "خصم فوق الحد أو تجاوز سعر أو مرتجع خارج السياسة أو إلغاء. يحضر المدير "
                    "ويُدخل الرمز، فيُسجَّل المستخدم والجهاز والإجراء والوقت."
                ),
                "tag": "gate",
                "dt": "AlphaX POS Manager Authorization Log",
            },
            {
                "t_en": "Run an X report mid-shift",
                "t_ar": "تقرير X أثناء الوردية",
                "d_en": (
                    "Supervisor-only. Shows running totals without closing the shift \u2014 "
                    "deliberately withheld from the cashier so the blind close stays blind."
                ),
                "d_ar": (
                    "للمشرف فقط. يعرض الإجماليات الجارية دون إقفال الوردية، ويُحجب عمداً عن "
                    "الكاشير حفاظاً على سرية الإقفال الأعمى."
                ),
                "dt": "X Report",
            },
            {
                "t_en": "Review the blind close",
                "t_ar": "مراجعة الإقفال الأعمى",
                "d_en": (
                    "See counted versus expected, recount with the cashier where needed, "
                    "then approve the variance or reject and reopen. Nothing closes silently."
                ),
                "d_ar": (
                    "مقارنة المعدود بالمتوقع، وإعادة العد مع الكاشير عند الحاجة، ثم اعتماد "
                    "الفرق أو الرفض وإعادة الفتح. ولا شيء يُقفل بصمت."
                ),
                "tag": "gate",
                "dt": "AlphaX POS Shift \u00b7 variance",
            },
            {
                "t_en": "Approve a handover",
                "t_ar": "اعتماد التسليم",
                "d_en": (
                    "Cashier A hands the desk to Cashier C mid-day. The day stays open under "
                    "the incoming cashier and the cash custody chain is unbroken."
                ),
                "d_ar": (
                    "يسلّم الكاشير (أ) المركز للكاشير (ج) أثناء اليوم، فيبقى اليوم مفتوحاً "
                    "تحت الكاشير الجديد دون انقطاع عهدة النقد."
                ),
                "dt": "AlphaX POS Shift \u00b7 handover",
            },
            {
                "t_en": "Close the trading day",
                "t_ar": "إقفال اليوم التجاري",
                "d_en": (
                    "One mutually-exclusive trigger per terminal: Manual, After N Shifts, or "
                    "At Closing Time. Handover closes never count toward N."
                ),
                "d_ar": (
                    "محفّز واحد فقط لكل جهاز: يدوي، أو بعد عدد ورديات، أو عند موعد الإغلاق. "
                    "ولا تُحتسب إقفالات التسليم ضمن العدد."
                ),
                "tag": "gate",
                "dt": "Day Close \u00b7 day_close_trigger",
            },
            {
                "t_en": "Distribute close notifications",
                "t_ar": "إرسال إشعارات الإقفال",
                "d_en": (
                    "Email natively, WhatsApp or SMS through the configured gateway, with "
                    "the shift-wise print report attached."
                ),
                "d_ar": (
                    "بالبريد أصلاً، أو واتساب أو رسالة نصية عبر البوابة المهيأة، مرفقاً بها "
                    "تقرير الورديات."
                ),
                "tag": "auto",
            },
            {
                "t_en": "Clear the sync queue",
                "t_ar": "تفريغ قائمة المزامنة",
                "d_en": (
                    "Pending offline sales must reach zero before the day is signed off. "
                    "Blocked entries are surfaced separately from transient retries."
                ),
                "d_ar": (
                    "يجب أن تصل المبيعات المعلّقة إلى صفر قبل اعتماد اليوم، مع فصل السجلات "
                    "المتوقفة عن المحاولات المؤقتة."
                ),
                "tag": "block",
                "dt": "Sync Queue",
            },
            {
                "t_en": "Check ZATCA status",
                "t_ar": "متابعة حالة هيئة الزكاة",
                "d_en": (
                    "Failed submissions are visible in the workspace and resubmitted from "
                    "there. A day is not clean until the queue is empty."
                ),
                "d_ar": (
                    "تظهر عمليات الإرسال الفاشلة في مساحة العمل ويُعاد إرسالها منها، ولا "
                    "يُعد اليوم مكتملاً حتى تفرغ القائمة."
                ),
                "dt": "ZATCA Status",
            },
            {
                "t_en": "Manage floor and readiness",
                "t_ar": "إدارة الصالة والجاهزية",
                "d_en": (
                    "Reset table readiness after clearing, and read turn-time from the "
                    "readiness-changed timestamps."
                ),
                "d_ar": (
                    "إعادة ضبط جاهزية الطاولة بعد التنظيف، وقراءة زمن الدوران من توقيتات "
                    "تغيّر الجاهزية."
                ),
                "dt": "AlphaX POS Table",
            },
            {
                "t_en": "Issue or adjust store credit",
                "t_ar": "إصدار أو تعديل رصيد المتجر",
                "d_en": (
                    "Store credit is an auditable liability ledger, not a points balance. "
                    "Issue, adjust and expiry each post a ledger entry."
                ),
                "d_ar": (
                    "رصيد المتجر التزام محاسبي قابل للتدقيق وليس نقاطاً. فالإصدار والتعديل "
                    "والانتهاء كلها تُرحَّل كقيود."
                ),
                "tag": "post",
                "dt": "Store Credit Ledger",
            },
            {
                "t_en": "Audit an employee",
                "t_ar": "تدقيق موظف",
                "d_en": (
                    "Filter the authorisation log by user to answer who approved what, at "
                    "which terminal, at what time."
                ),
                "d_ar": (
                    "تصفية سجل التفويض حسب المستخدم لمعرفة من اعتمد ماذا وعلى أي جهاز وفي "
                    "أي وقت."
                ),
                "dt": "Authorization Log \u00b7 Shift Register",
            },
        ],
    },
    {
        "id": "kitchen",
        "role": R_KITCHEN,
        "name_en": "Kitchen / KDS Operator",
        "name_ar": "المطبخ / شاشة التحضير",
        "scope_en": (
            "Sees tickets and items only. No prices, no totals, no customer payment "
            "data ever reaches this screen."
        ),
        "scope_ar": (
            "يرى التذاكر والأصناف فقط. ولا تصل الأسعار أو الإجماليات أو بيانات الدفع إلى "
            "هذه الشاشة إطلاقاً."
        ),
        "chips": ["KDS v2", "Print Station", "KOT Routing Rule"],
        "steps": [
            {
                "t_en": "Receive the ticket",
                "t_ar": "استلام التذكرة",
                "d_en": (
                    "Routing rules decide the station. The ticket arrives over realtime on "
                    "the KDS and, where configured, on the station printer."
                ),
                "d_ar": (
                    "تحدد قواعد التوجيه المحطة، فتصل التذكرة فورياً إلى شاشة التحضير وإلى "
                    "طابعة المحطة عند تهيئتها."
                ),
                "tag": "auto",
                "dt": "KOT Routing Rule",
            },
            {
                "t_en": "Start preparing",
                "t_ar": "بدء التحضير",
                "d_en": (
                    "Moving a ticket to preparing stamps the start time, which is what "
                    "turn-time and throughput reporting is built on."
                ),
                "d_ar": (
                    "نقل التذكرة إلى قيد التحضير يسجّل وقت البدء، وعليه تُبنى تقارير زمن "
                    "الدوران والإنتاجية."
                ),
                "dt": "KDS ticket state",
            },
            {
                "t_en": "Bump items individually",
                "t_ar": "إنهاء الأصناف فردياً",
                "d_en": (
                    "Item-level state lets a station finish part of a ticket while the rest "
                    "stays live at another station."
                ),
                "d_ar": (
                    "حالة على مستوى الصنف تتيح لمحطة إنهاء جزء من التذكرة بينما يبقى الباقي "
                    "نشطاً في محطة أخرى."
                ),
                "dt": "item_states",
            },
            {
                "t_en": "Mark ready and dispatch",
                "t_ar": "الجاهزية والتسليم",
                "d_en": (
                    "Ready hands the order back to the floor and updates the customer "
                    "display board."
                ),
                "d_ar": "الجاهزية تُعيد الطلب إلى الصالة وتُحدّث شاشة العميل.",
                "dt": "Customer Display",
            },
            {
                "t_en": "Recall a bumped ticket",
                "t_ar": "استرجاع تذكرة منتهية",
                "d_en": (
                    "A bumped ticket can be pulled back on the station without involving "
                    "the cashier or touching the invoice."
                ),
                "d_ar": (
                    "يمكن استرجاع التذكرة المنتهية من المحطة دون الرجوع للكاشير أو المساس "
                    "بالفاتورة."
                ),
                "dt": "KDS recall",
            },
        ],
    },
    {
        "id": "accounts",
        "role": R_ACCOUNTS,
        "name_en": "Accounts / Back Office",
        "name_ar": "الحسابات / الإدارة الخلفية",
        "scope_en": (
            "Never touches the till. Consumes what the till produced and owns "
            "everything downstream of the day close."
        ),
        "scope_ar": (
            "لا يتعامل مع الصندوق إطلاقاً، بل يستقبل مخرجاته ويتولى كل ما بعد إقفال اليوم."
        ),
        "chips": ["Sales Invoice", "GL Entry", "Shift Register", "Store Credit Ledger"],
        "steps": [
            {
                "t_en": "Review the day close",
                "t_ar": "مراجعة إقفال اليوم",
                "d_en": (
                    "Read the shift-wise report: who held the desk, opening float, counted "
                    "cash, over or short, and which day close it rolled into."
                ),
                "d_ar": (
                    "قراءة تقرير الورديات: من تولى المركز، والرصيد الافتتاحي، والنقد المعدود، "
                    "والزيادة أو العجز، وإقفال اليوم المرتبط."
                ),
                "dt": "AlphaX POS Shift Register",
            },
            {
                "t_en": "Reconcile cash to bank",
                "t_ar": "مطابقة النقد مع البنك",
                "d_en": (
                    "Match counted cash against the deposit, and post approved variances to "
                    "the write-off account by journal entry."
                ),
                "d_ar": (
                    "مطابقة النقد المعدود مع الإيداع، وترحيل الفروق المعتمدة إلى حساب الشطب "
                    "بقيد يومية."
                ),
                "tag": "post",
                "dt": "Journal Entry",
            },
            {
                "t_en": "Verify the tobacco fee reposting",
                "t_ar": "التحقق من ترحيل رسوم التبغ",
                "d_en": (
                    "The invoice stays a plain inclusive 15% document; the fee is moved from "
                    "income to the liability account by journal entry on submit and reversed "
                    "on cancel."
                ),
                "d_ar": (
                    "تبقى الفاتورة مستنداً شاملاً بنسبة ١٥٪، وتُنقل الرسوم من الإيراد إلى حساب "
                    "الالتزام بقيد عند الترحيل ويُعكس عند الإلغاء."
                ),
                "tag": "post",
                "dt": "Journal Entry \u00b7 tobacco fee",
            },
            {
                "t_en": "Review the store credit liability",
                "t_ar": "مراجعة التزام رصيد المتجر",
                "d_en": (
                    "Outstanding store credit is a real liability balance. Expiry is written "
                    "as a ledger entry, not a silent field update, so the release of the "
                    "liability is auditable."
                ),
                "d_ar": (
                    "رصيد المتجر القائم التزام فعلي، وانتهاؤه يُسجَّل كقيد لا كتعديل صامت، "
                    "ليبقى تحرير الالتزام قابلاً للتدقيق."
                ),
                "dt": "Store Credit Ledger",
            },
            {
                "t_en": "Run the ZATCA audit",
                "t_ar": "تدقيق هيئة الزكاة",
                "d_en": (
                    "Confirm every submitted invoice for the period was accepted, and clear "
                    "anything still sitting in the failure queue."
                ),
                "d_ar": (
                    "التأكد من قبول كل فاتورة مُرسلة خلال الفترة، ومعالجة ما تبقى في قائمة "
                    "الإخفاق."
                ),
                "dt": "ZATCA Audit",
            },
            {
                "t_en": "Close the period",
                "t_ar": "إقفال الفترة",
                "d_en": (
                    "Standard ERPNext period closing. Because the till posted into the same "
                    "ledger all along, there is nothing to import and nothing to reconcile "
                    "across systems."
                ),
                "d_ar": (
                    "إقفال الفترة بالطريقة المعتادة في إي آر بي نكست. ولأن الصندوق كان يُرحّل "
                    "إلى الدفاتر نفسها، فلا استيراد ولا مطابقة بين أنظمة."
                ),
                "tag": "post",
                "dt": "Period Closing Voucher",
            },
        ],
    },
    {
        "id": "admin",
        "role": R_ADMIN,
        "name_en": "Administrator",
        "name_ar": "مسؤول النظام",
        "scope_en": "Sets the structure everyone else operates inside. Never rings a sale in production.",
        "scope_ar": "يبني الهيكل الذي يعمل الجميع ضمنه، ولا ينفّذ عمليات بيع في بيئة الإنتاج.",
        "chips": ["Onboarding Wizard", "POS Profile", "verify_tree.py", "Frappe Cloud"],
        "steps": [
            {
                "t_en": "Install and run the onboarding wizard",
                "t_ar": "التثبيت وتشغيل معالج التهيئة",
                "d_en": (
                    "A step state machine walks the whole setup. Idempotent after_install and "
                    "after_migrate seeders mean a re-run never duplicates data."
                ),
                "d_ar": (
                    "آلة حالات تُنفّذ التهيئة خطوة بخطوة، مع مُهيّئات متكررة الأمان لا تُكرّر "
                    "البيانات عند إعادة التشغيل."
                ),
                "dt": "Onboarding Wizard",
            },
            {
                "t_en": "Build the hierarchy",
                "t_ar": "بناء الهيكل التنظيمي",
                "d_en": (
                    "Company \u2192 Branch \u2192 Outlet \u2192 Terminal. Session scope is "
                    "branch-first, so a user sees only their branch's data."
                ),
                "d_ar": (
                    "الشركة \u2190 الفرع \u2190 المنفذ \u2190 نقطة البيع. ونطاق الجلسة يبدأ من "
                    "الفرع، فلا يرى المستخدم سوى بيانات فرعه."
                ),
                "dt": "AlphaX POS Outlet \u00b7 Terminal",
            },
            {
                "t_en": "Configure the POS Profile",
                "t_ar": "تهيئة ملف نقطة البيع",
                "d_en": (
                    "The POS Profile is terminal accounting configuration, not user identity "
                    "\u2014 income account, payment modes, warehouse, price list."
                ),
                "d_ar": (
                    "ملف نقطة البيع تهيئة محاسبية للجهاز وليس هوية مستخدم \u2014 حساب الإيراد "
                    "وطرق الدفع والمستودع وقائمة الأسعار."
                ),
                "dt": "POS Profile",
            },
            {
                "t_en": "Set taxes, pricing and menus",
                "t_ar": "ضبط الضرائب والأسعار والقوائم",
                "d_en": (
                    "Inclusive VAT templates, channel pricing per order type, and menus "
                    "expressed as set algebra over item groups rather than flat lists."
                ),
                "d_ar": (
                    "قوالب ضريبة مشمولة، وتسعير لكل قناة حسب نوع الطلب، وقوائم مبنية على "
                    "عمليات مجموعات لا قوائم مسطحة."
                ),
                "dt": "Item Tax Template \u00b7 AlphaX POS Menu",
            },
            {
                "t_en": "Run the hardware wizard",
                "t_ar": "تشغيل معالج الأجهزة",
                "d_en": (
                    "Print stations, KOT routing rules, single-printer merge mode, cash drawer "
                    "and the AlphaX POS Bridge agent on each Windows station."
                ),
                "d_ar": (
                    "محطات الطباعة وقواعد التوجيه ووضع الطابعة المفردة ودرج النقد ووكيل الجسر "
                    "على كل جهاز ويندوز."
                ),
                "dt": "Print Station \u00b7 POS Bridge",
            },
            {
                "t_en": "Create users, roles and PINs",
                "t_ar": "إنشاء المستخدمين والأدوار والرموز",
                "d_en": (
                    "Assign the AlphaX roles, then issue manager PINs. Custom DocPerm rows must "
                    "never lock System Manager out \u2014 a migrate hook heals this automatically."
                ),
                "d_ar": (
                    "إسناد أدوار ألفا إكس ثم إصدار رموز المدراء. ويجب ألا تحجب صلاحيات مخصصة "
                    "مسؤول النظام \u2014 ويعالج خطاف الترحيل ذلك تلقائياً."
                ),
                "tag": "block",
                "dt": "Custom DocPerm \u00b7 heal_lost_manager_access",
            },
            {
                "t_en": "Generate table QR tokens",
                "t_ar": "توليد رموز الطاولات",
                "d_en": "One click per table or per outlet produces the printable QR sheet for customer ordering.",
                "d_ar": "نقرة واحدة لكل طاولة أو منفذ تُنتج ورقة الرموز القابلة للطباعة لطلبات العملاء.",
                "dt": "ensure_table_token \u00b7 /table_qr",
            },
            {
                "t_en": "Complete ZATCA onboarding",
                "t_ar": "إتمام تسجيل هيئة الزكاة",
                "d_en": (
                    "OTP, CSR generation, compliance CSID then production CSID, with environment "
                    "switching between simulation and production."
                ),
                "d_ar": (
                    "رمز التحقق وتوليد الطلب ثم الشهادة التجريبية فالإنتاجية، مع التبديل بين "
                    "بيئتي المحاكاة والإنتاج."
                ),
                "dt": "ZATCA Settings",
            },
            {
                "t_en": "Deploy and verify",
                "t_ar": "النشر والتحقق",
                "d_en": (
                    "GitHub push triggers the Frappe Cloud migration. verify_tree.py runs its "
                    "structural guards \u2014 packaging, doctype JSON, Select options, permission "
                    "lockout, Vue imports, payload freshness, Python parse."
                ),
                "d_ar": (
                    "دفع التحديث إلى GitHub يُشغّل الترحيل على فرابي كلاود، ويُنفّذ المدقق الهيكلي "
                    "فحوصه: التغليف وملفات الدوكتايب وخيارات الاختيار وحجب الصلاحيات واستيرادات "
                    "Vue وحداثة البيانات وصحة الكود."
                ),
                "tag": "auto",
                "dt": "verify_tree.py",
            },
        ],
    },
    {
        "id": "customer",
        "role": "Guest (no role)",
        "name_en": "Customer (QR ordering)",
        "name_ar": "العميل (الطلب بالرمز)",
        "scope_en": (
            "Unauthenticated guest holding a table token. Sees a server-priced menu and "
            "nothing else \u2014 no stock, no cost, no other tables."
        ),
        "scope_ar": (
            "ضيف غير مسجّل يحمل رمز طاولة. يرى قائمة مُسعّرة من الخادم فقط \u2014 دون مخزون "
            "أو تكلفة أو طاولات أخرى."
        ),
        "chips": ["/bonanza_order", "get_qr_menu", "Customer Display"],
        "steps": [
            {
                "t_en": "Scan the table QR",
                "t_ar": "مسح رمز الطاولة",
                "d_en": (
                    "The token identifies the table and outlet. No login, and the token is "
                    "scoped so it cannot reach another table's session."
                ),
                "d_ar": (
                    "يحدد الرمز الطاولة والمنفذ دون تسجيل دخول، وهو مقيّد بحيث لا يصل إلى جلسة "
                    "طاولة أخرى."
                ),
                "dt": "ensure_table_token",
            },
            {
                "t_en": "Browse the menu",
                "t_ar": "تصفح القائمة",
                "d_en": (
                    "Prices come from the server against the order type's channel price list. "
                    "The client is never trusted with pricing."
                ),
                "d_ar": (
                    "تأتي الأسعار من الخادم وفق قائمة أسعار القناة لنوع الطلب، ولا يُعتمد على "
                    "الجهاز في التسعير إطلاقاً."
                ),
                "tag": "auto",
                "dt": "get_qr_menu",
            },
            {
                "t_en": "Place the order",
                "t_ar": "إرسال الطلب",
                "d_en": (
                    "The order lands on the cashier screen for acceptance. A guest can never "
                    "submit an invoice or take a payment path directly."
                ),
                "d_ar": (
                    "يصل الطلب إلى شاشة الكاشير للاعتماد، ولا يمكن للضيف ترحيل فاتورة أو الدخول "
                    "لمسار الدفع مباشرة."
                ),
                "tag": "block",
            },
            {
                "t_en": "Watch the display board",
                "t_ar": "متابعة شاشة العرض",
                "d_en": (
                    "Order progress is announced bilingually by voice and shown on the board as "
                    "the kitchen advances the ticket."
                ),
                "d_ar": (
                    "يُعلن تقدم الطلب صوتياً بالعربية والإنجليزية ويُعرض على الشاشة مع تقدم المطبخ "
                    "في التذكرة."
                ),
                "dt": "Customer Display",
            },
        ],
    },
]

#: Column order of :data:`MATRIX` values, aligned to :data:`LANES`.
LANE_IDS = [lane["id"] for lane in LANES]

# --------------------------------------------------------------------------
# Permission matrix. Values: y (permitted), pin (manager authorisation),
# view (read only), n (not permitted). One entry per lane, in LANE_IDS order.
# --------------------------------------------------------------------------

# Columns, in LANE_IDS order:
#   cashier, supervisor, manager, kitchen, accounts, admin, customer
#
# Values are taken from the code, not from intent:
#   posting.py          _ensure_role_allowed / approval_status
#   shift_api.py        _MANAGER_ROLES (includes Supervisor)
#   manager_pin.py      MANAGER_ROLES   (excludes Supervisor)
#   doctype JSON        AlphaX POS Shift / KDS Ticket / Authorization Log
MATRIX = [
    ("Open a shift / declare opening float", "فتح وردية وإدخال الرصيد الافتتاحي",
     ["y", "y", "y", "n", "n", "y", "n"]),
    ("Open a shift on behalf of another user", "فتح وردية نيابة عن مستخدم آخر",
     ["n", "y", "y", "n", "n", "y", "n"]),
    ("Ring up a sale", "تنفيذ عملية بيع",
     ["y", "y", "y", "n", "n", "y", "n"]),
    ("Discount within threshold", "خصم ضمن الحد المسموح",
     ["y", "y", "y", "n", "n", "y", "n"]),
    ("Discount above threshold", "خصم يتجاوز الحد",
     ["pin", "pin", "y", "n", "n", "y", "n"]),
    ("Override an item price", "تجاوز سعر صنف",
     ["pin", "pin", "y", "n", "n", "y", "n"]),
    ("Approve an order flagged for approval", "اعتماد طلب موقوف للمراجعة",
     ["n", "n", "y", "n", "n", "y", "n"]),
    ("Return within policy", "مرتجع ضمن السياسة",
     ["y", "y", "y", "n", "n", "y", "n"]),
    ("Return outside policy window", "مرتجع خارج مدة السياسة",
     ["pin", "pin", "y", "n", "n", "y", "n"]),
    ("Edit a credit note amount", "تعديل مبلغ إشعار دائن",
     ["n", "n", "y", "n", "view", "y", "n"]),
    ("Void or cancel a submitted sale", "إلغاء عملية بيع مرحّلة",
     ["pin", "pin", "y", "n", "view", "y", "n"]),
    ("Send / reprint a KOT", "إرسال أو إعادة طباعة قسيمة المطبخ",
     ["y", "y", "y", "y", "n", "y", "n"]),
    ("Advance a KDS ticket state", "تغيير حالة تذكرة شاشة التحضير",
     ["n", "n", "y", "y", "n", "y", "n"]),
    ("View running totals mid-shift (X report)", "عرض الإجماليات الجارية (تقرير X)",
     ["n", "y", "y", "n", "n", "y", "n"]),
    ("Enter counted cash at close", "إدخال النقد المعدود عند الإقفال",
     ["y", "y", "y", "n", "n", "y", "n"]),
    ("See expected cash at close", "رؤية النقد المتوقع عند الإقفال",
     ["n", "y", "y", "n", "view", "y", "n"]),
    ("Approve a cash variance", "اعتماد فرق نقدي",
     ["n", "y", "y", "n", "n", "y", "n"]),
    ("Hand over the desk mid-day", "تسليم المركز أثناء اليوم",
     ["y", "y", "y", "n", "n", "y", "n"]),
    ("Trigger day close", "تنفيذ إقفال اليوم",
     ["n", "y", "y", "n", "view", "y", "n"]),
    ("Bind or rebind a terminal", "ربط أو إعادة ربط جهاز",
     ["pin", "pin", "y", "n", "n", "y", "n"]),
    ("Hold or reset a manager PIN", "حمل أو إعادة ضبط رمز المدير",
     ["n", "n", "y", "n", "n", "y", "n"]),
    ("Read the authorisation log", "الاطلاع على سجل التفويض",
     ["n", "n", "y", "n", "n", "y", "n"]),
    ("Create a table on the fly", "إنشاء طاولة فورياً",
     ["y", "y", "y", "n", "n", "y", "n"]),
    ("Reset table readiness", "إعادة ضبط جاهزية الطاولة",
     ["y", "y", "y", "y", "n", "y", "n"]),
    ("Generate table QR tokens", "توليد رموز الطاولات",
     ["n", "y", "y", "n", "n", "y", "n"]),
    ("Redeem store credit at the till", "خصم رصيد المتجر عند الصندوق",
     ["y", "y", "y", "n", "n", "y", "n"]),
    ("Issue or adjust store credit", "إصدار أو تعديل رصيد المتجر",
     ["n", "n", "y", "n", "y", "y", "n"]),
    ("Resubmit a failed ZATCA document", "إعادة إرسال مستند زكاة فاشل",
     ["n", "n", "y", "n", "y", "y", "n"]),
    ("Clear the offline sync queue", "معالجة قائمة المزامنة",
     ["n", "y", "y", "n", "n", "y", "n"]),
    ("Post a journal entry", "ترحيل قيد يومية",
     ["n", "n", "n", "n", "y", "y", "n"]),
    ("Close an accounting period", "إقفال فترة محاسبية",
     ["n", "n", "n", "n", "y", "y", "n"]),
    ("Edit POS Profile / tax templates", "تعديل ملف نقطة البيع والضرائب",
     ["n", "n", "n", "n", "view", "y", "n"]),
    ("Place an order from a table QR", "إرسال طلب عبر رمز الطاولة",
     ["y", "y", "y", "n", "n", "y", "y"]),
]


# --------------------------------------------------------------------------
# Resolution
# --------------------------------------------------------------------------


def _roles(user: str | None = None) -> set:
    """Roles held by ``user``, defaulting to the session user."""
    return set(frappe.get_roles(user or frappe.session.user))


def visible_lane_ids(user: str | None = None) -> list:
    """Lane ids this user may read.

    A supervisor sees every lane including the reference-only guest lane.
    Everyone else sees exactly the lanes matching a role they actually hold,
    which for a cashier means one lane and nothing else.
    """
    held = _roles(user)

    if held & SUPERVISORY_ROLES:
        return list(LANE_IDS)

    extra = set()
    for role, lanes in EXTRA_LANES.items():
        if role in held:
            extra.update(lanes)

    out = [
        lane["id"] for lane in LANES
        if lane["id"] not in REFERENCE_LANES
        and (lane["role"] in held or lane["id"] in extra)
    ]
    return out


def get_context_payload(user: str | None = None) -> dict:
    """Everything the page or the SPA needs, already filtered.

    Lanes the viewer may not see are absent from the payload, not hidden in
    it. The matrix is trimmed to the viewer's own column unless they hold a
    role entitled to read the whole grid.
    """
    ids = visible_lane_ids(user)
    lanes = [lane for lane in LANES if lane["id"] in ids]

    held = _roles(user)
    full_matrix = bool(held & FULL_MATRIX_ROLES)

    # Columns are lane ids; for a full-matrix viewer that is all of them,
    # otherwise only the viewer's own lanes.
    columns = list(LANE_IDS) if full_matrix else ids
    col_index = [LANE_IDS.index(c) for c in columns]

    matrix = [
        {
            "a_en": a_en,
            "a_ar": a_ar,
            "v": [vals[i] for i in col_index],
        }
        for a_en, a_ar, vals in MATRIX
    ]

    # Drop rows that say nothing to this viewer: if every visible cell is
    # "not permitted", the row is noise on a cashier's screen.
    if not full_matrix:
        matrix = [row for row in matrix if any(v != "n" for v in row["v"])]

    return {
        "lanes": lanes,
        "columns": [
            {
                "id": LANES[i]["id"],
                "name_en": LANES[i]["name_en"],
                "name_ar": LANES[i]["name_ar"],
            }
            for i in col_index
        ],
        "matrix": matrix,
        "full_matrix": full_matrix,
        "user_roles": sorted(held & ({lane["role"] for lane in LANES} | SUPERVISORY_ROLES)),
        "has_access": bool(lanes),
    }


@frappe.whitelist()
def get_flow() -> dict:
    """Filtered flow payload for the cashier SPA or onboarding help.

    Whitelisted but not guest-exposed: an anonymous caller gets nothing,
    because ``visible_lane_ids`` resolves no lanes for the Guest user.
    """
    if frappe.session.user == "Guest":
        frappe.throw(_("Not permitted"), frappe.PermissionError)
    return get_context_payload()
