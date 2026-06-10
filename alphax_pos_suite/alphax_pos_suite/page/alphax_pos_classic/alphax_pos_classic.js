frappe.pages['alphax-pos-classic'].on_page_load = function(wrapper) {
  frappe.ui.make_app_page({ parent: wrapper, title: 'AlphaX POS Classic', single_column: true });

  const LS_KEY = 'alphax_pos_offline_queue_v1';
  const state = { cart: [], payments: [], settings: null };

  const $root = $(wrapper).find('.layout-main-section');
  // Add a body class so our scoped CSS only styles this page
  $('body').addClass('alphax-pos-classic-page');

  $root.html(`
    <div class="alphax-pos-shell">
      <!-- Top bar: title + action buttons -->
      <div class="alphax-pos-topbar">
        <div class="alphax-pos-title">
          <div class="alphax-pos-eyebrow">Barcode scan • Pricing rules • Offline queue • Shifts • Credit note redeem</div>
          <h1>AlphaX POS</h1>
        </div>
        <div class="alphax-pos-toolbar">
          <button class="alphax-btn alphax-btn-ghost" data-action="shift_list">
            <span class="alphax-btn-icon">📋</span>Shifts
          </button>
          <button class="alphax-btn alphax-btn-ghost" data-action="cash_moves">
            <span class="alphax-btn-icon">💵</span>Cash Moves
          </button>
          <button class="alphax-btn alphax-btn-primary" data-action="sync_queue">
            <span class="alphax-btn-icon">↻</span>Sync Queue
          </button>
          <button class="alphax-btn alphax-btn-ghost alphax-btn-icon-only" data-action="manager_setup" title="Manager Setup">
            <span class="alphax-btn-icon">⚙</span>
          </button>
        </div>
      </div>

      <!-- Station-not-configured card (shown when no terminal in localStorage) -->
      <div class="alphax-station-not-configured" data-area="not_configured" style="display:none">
        <div class="alphax-not-configured-icon">🔒</div>
        <h2>Station Not Configured</h2>
        <p>This computer hasn't been bound to a POS terminal yet. A manager must complete a one-time setup before this station can take orders.</p>
        <button class="alphax-btn alphax-btn-primary alphax-btn-pay" data-action="manager_setup">
          <span class="alphax-btn-icon">⚙</span>Manager Setup
        </button>
        <p class="alphax-not-configured-hint">A manager will be asked to enter their username and PIN.</p>
      </div>

      <!-- Cashier UI wrapper - hidden until terminal is bound -->
      <div data-area="cashier_ui" style="display:none">

      <!-- Active station banner (terminal/outlet/branch) -->
      <div class="alphax-station-banner" data-area="station_banner">
        <div class="alphax-station-info">
          <div class="alphax-station-label">Station</div>
          <div class="alphax-station-value" data-area="station_value">Loading…</div>
        </div>
      </div>

      <!-- Order entry card -->
      <div class="alphax-card alphax-card-entry">
        <div class="alphax-card-body">
          <div class="alphax-field-grid">
            <div class="alphax-field">
              <label>Terminal</label>
              <input class="alphax-input" data-field="terminal" placeholder="AlphaX POS Terminal"/>
            </div>
            <div class="alphax-field">
              <label>Customer</label>
              <input class="alphax-input" data-field="customer" placeholder="Customer"/>
            </div>
            <div class="alphax-field">
              <label>Offer Code</label>
              <input class="alphax-input" data-field="offer_code" placeholder="COUPON"/>
            </div>
            <div class="alphax-field alphax-field-scan">
              <label>Scan / Item Code</label>
              <input class="alphax-input" data-field="scan" placeholder="Scan barcode or type item code + Enter"/>
            </div>
          </div>
          <div class="alphax-action-row">
            <div class="alphax-field alphax-field-qty">
              <label>Qty</label>
              <input class="alphax-input" data-field="qty" type="number" value="1" min="1"/>
            </div>
            <div class="alphax-action-buttons">
              <button class="alphax-btn alphax-btn-ghost" data-action="add_item">
                <span class="alphax-btn-icon">+</span>Add
              </button>
              <button class="alphax-btn alphax-btn-ghost" data-action="hold">Hold</button>
              <button class="alphax-btn alphax-btn-primary alphax-btn-pay" data-action="submit">
                <span class="alphax-btn-icon">✓</span>Pay &amp; Submit
              </button>
              <button class="alphax-btn alphax-btn-danger" data-action="return">Return</button>
            </div>
          </div>
        </div>
      </div>

      <!-- Two-column layout: cart+payments | sidebar -->
      <div class="alphax-pos-grid">
        <div class="alphax-pos-main">
          <!-- Cart -->
          <div class="alphax-card">
            <div class="alphax-card-header">
              <h3>Cart</h3>
            </div>
            <div class="alphax-card-body">
              <div data-area="cart"></div>
            </div>
            <div class="alphax-card-footer alphax-total-row">
              <div class="alphax-total-label">Total</div>
              <div class="alphax-total-value">
                <span data-area="total">0.00</span>
                <span class="alphax-total-currency" title="Saudi Riyal">&#xea;</span>
              </div>
            </div>
          </div>

          <!-- Payments -->
          <div class="alphax-card">
            <div class="alphax-card-header">
              <h3>Payments</h3>
              <div class="alphax-button-pair">
                <button class="alphax-btn alphax-btn-ghost alphax-btn-sm" data-action="pay_by_card">
                  💳 Pay by Card
                </button>
                <button class="alphax-btn alphax-btn-ghost alphax-btn-sm" data-action="add_credit_note">
                  Redeem Credit Note
                </button>
              </div>
            </div>
            <div class="alphax-card-body">
              <div class="alphax-field-grid alphax-payment-grid">
                <div class="alphax-field">
                  <label>Mode of Payment</label>
                  <select class="alphax-input" data-field="mop"></select>
                  <small class="alphax-hint">Loaded from ERPNext Mode of Payment</small>
                </div>
                <div class="alphax-field">
                  <label>Amount</label>
                  <input class="alphax-input" data-field="amt" type="number"/>
                </div>
                <div class="alphax-field alphax-field-action">
                  <label>&nbsp;</label>
                  <button class="alphax-btn alphax-btn-primary alphax-btn-block" data-action="add_payment">
                    Add Payment
                  </button>
                </div>
              </div>
              <div data-area="payments" class="alphax-payment-list"></div>
            </div>
          </div>
        </div>

        <!-- Right sidebar -->
        <div class="alphax-pos-side">
          <!-- Held Invoices -->
          <div class="alphax-card">
            <div class="alphax-card-header">
              <h3>Held Invoices</h3>
              <button class="alphax-btn alphax-btn-ghost alphax-btn-sm" data-action="refresh_holds">↻ Refresh</button>
            </div>
            <div class="alphax-card-body">
              <div data-area="holds"></div>
            </div>
          </div>

          <!-- Offline Queue -->
          <div class="alphax-card">
            <div class="alphax-card-header">
              <h3>Offline Queue</h3>
              <div class="alphax-button-pair">
                <button class="alphax-btn alphax-btn-ghost alphax-btn-sm" data-action="show_queue">Show</button>
                <button class="alphax-btn alphax-btn-danger alphax-btn-sm" data-action="clear_queue">Clear</button>
              </div>
            </div>
            <div class="alphax-card-body">
              <div data-area="queue"></div>
            </div>
          </div>
        </div>
      </div>
      </div> <!-- /cashier_ui -->
    </div>
  `);

  function get_queue(){ try { return JSON.parse(localStorage.getItem(LS_KEY)||'[]'); } catch(e){ return []; } }
  function set_queue(q){ localStorage.setItem(LS_KEY, JSON.stringify(q||[])); }
  function queue_push(payload){ const q=get_queue(); q.push({id:frappe.utils.get_random(10), created_on:new Date().toISOString(), payload}); set_queue(q); }

  function ui_total(){
    let t=0; state.cart.forEach(r=>t += (r.qty*r.rate));
    $(wrapper).find('[data-area="total"]').text(t.toFixed(2));
    return t;
  }

  function render_cart(){
    const $c=$(wrapper).find('[data-area="cart"]');
    if(!state.cart.length){
      $c.html('<div class="alphax-empty-state">🛒 Cart is empty. Scan a barcode or enter an item code above.</div>');
      ui_total();
      return;
    }
    $c.html(state.cart.map((r,idx)=>`
      <div class="alphax-cart-line">
        <div class="alphax-cart-line-info">
          <div class="alphax-cart-line-name">${frappe.utils.escape_html(r.item_code)}</div>
          <div class="alphax-cart-line-meta">
            <span>Rate: <b>${r.rate}</b></span>
            <span class="alphax-dot">•</span>
            <span>Qty: <b>${r.qty}</b></span>
            <span class="alphax-dot">•</span>
            <span>Subtotal: <b>${(r.rate * r.qty).toFixed(2)}</b></span>
          </div>
        </div>
        <div class="alphax-cart-line-actions">
          <button class="alphax-qty-btn" data-action="dec" data-idx="${idx}" title="Decrease">−</button>
          <span class="alphax-qty-display">${r.qty}</span>
          <button class="alphax-qty-btn" data-action="inc" data-idx="${idx}" title="Increase">+</button>
          <button class="alphax-qty-btn alphax-qty-remove" data-action="rm" data-idx="${idx}" title="Remove">×</button>
        </div>
      </div>
    `).join(''));
    ui_total();
  }

  function render_payments(){
    const $p=$(wrapper).find('[data-area="payments"]');
    if(!state.payments.length){
      $p.html('<div class="alphax-empty-state alphax-empty-small">No payments added yet.</div>');
      return;
    }
    $p.html(state.payments.map((p,idx)=>{
      const title = p.payment_type === 'Credit Note Redeem'
        ? `Credit Note: ${p.credit_note}`
        : p.mode_of_payment;
      const subtitle = p.payment_type === 'Credit Note Redeem'
        ? `Available: ${p.credit_available}`
        : '';
      return `<div class="alphax-payment-line">
        <div class="alphax-payment-info">
          <div class="alphax-payment-title">${frappe.utils.escape_html(title)}</div>
          ${subtitle ? `<div class="alphax-payment-subtitle">${frappe.utils.escape_html(subtitle)}</div>` : ''}
        </div>
        <div class="alphax-payment-amount">${parseFloat(p.amount).toFixed(2)}</div>
        <button class="alphax-qty-btn alphax-qty-remove" data-action="rm_pay" data-idx="${idx}" title="Remove">×</button>
      </div>`;
    }).join(''));
  }

  
async function load_mops(){
  const $sel=$(wrapper).find('[data-field="mop"]');
  $sel.html('<option value="">Select…</option>');
  try{
    const res=await frappe.call({
      method:'frappe.client.get_list',
      args:{doctype:'Mode of Payment', fields:['name','type','enabled'], filters:{enabled:1}, limit_page_length:200, order_by:'name asc'}
    });
    (res.message||[]).forEach(r=>{
      $sel.append(`<option value="${frappe.utils.escape_html(r.name)}">${frappe.utils.escape_html(r.name)}</option>`);
    });
  }catch(e){
    // fallback options
    ['Cash','Debit Card','Credit Card','MADA','STC Pay'].forEach(x=>$sel.append(`<option value="${x}">${x}</option>`));
  }
}

async function load_settings(){
    try{
      const r=await frappe.call({method:'frappe.client.get', args:{doctype:'AlphaX POS Settings', name:'AlphaX POS Settings'}});
      state.settings=r.message;
    }catch(e){}
  }

  async function pricing_get(item_code){
    try{
      const terminal=$(wrapper).find('[data-field="terminal"]').val().trim();
      const customer=$(wrapper).find('[data-field="customer"]').val().trim();
      let company=null, price_list=null;
      if(terminal){
        const t=await frappe.db.get_value('AlphaX POS Terminal', terminal, ['pos_outlet']);
        if(t && t.message && t.message.pos_outlet){
          const o=await frappe.db.get_value('AlphaX POS Outlet', t.message.pos_outlet, ['company','default_price_list']);
          company=o.message.company; price_list=o.message.default_price_list;
        }
      }
      const res=await frappe.call({ method:'erpnext.stock.get_item_details.get_item_details', args:{ args:{ item_code, qty:1, company, customer, price_list } } });
      const det=res.message||{};
      return det.rate || det.price_list_rate || 1;
    }catch(e){ return 1; }
  }

  async function add_item(){
    const code=$(wrapper).find('[data-field="scan"]').val().trim();
    const qty=parseFloat($(wrapper).find('[data-field="qty"]').val()||1);
    if(!code) return;
    const rate=await pricing_get(code);
    state.cart.push({item_code:code, qty, rate});
    $(wrapper).find('[data-field="scan"]').val('');
    render_cart();
  }

  async function refresh_holds(){
    const $h=$(wrapper).find('[data-area="holds"]');
    $h.html('<div class="alphax-empty-state alphax-empty-small">Loading…</div>');
    const res=await frappe.call({ method:'frappe.client.get_list',
      args:{ doctype:'AlphaX POS Order', fields:['name','customer','modified'], filters:{docstatus:0, order_status:'Hold'}, order_by:'modified desc', limit_page_length:20 }});
    const rows=(res.message||[]).map(d=>`
      <div class="alphax-list-item">
        <div class="alphax-list-item-info">
          <div class="alphax-list-item-title">${frappe.utils.escape_html(d.name)}</div>
          <div class="alphax-list-item-subtitle">${frappe.utils.escape_html(d.customer || 'No customer')}</div>
        </div>
        <a class="alphax-btn alphax-btn-ghost alphax-btn-sm" href="#Form/AlphaX POS Order/${frappe.utils.escape_html(d.name)}">Open</a>
      </div>
    `).join('');
    $h.html(rows || '<div class="alphax-empty-state alphax-empty-small">No held invoices.</div>');
  }

  function render_queue(){
    const q=get_queue();
    const $q=$(wrapper).find('[data-area="queue"]');
    if(!q.length){
      $q.html('<div class="alphax-empty-state alphax-empty-small">Queue empty.</div>');
      return;
    }
    $q.html(q.map(x=>`
      <div class="alphax-list-item">
        <div class="alphax-list-item-info">
          <div class="alphax-list-item-title">${frappe.utils.escape_html(x.id)}</div>
          <div class="alphax-list-item-subtitle">${frappe.utils.escape_html(x.created_on)}</div>
          <div class="alphax-list-item-detail">${frappe.utils.escape_html(JSON.stringify(x.payload).slice(0,120))}…</div>
        </div>
      </div>
    `).join(''));
  }

  async function sync_queue(){
    const q=get_queue();
    if(!q.length) return frappe.msgprint('Queue is empty.');
    let ok=0, fail=0; const remaining=[];
    for(const it of q){
      try{
        const ins=await frappe.call({method:'frappe.client.insert', args:{doc: it.payload.doc}});
        const name=ins.message.name;
        if(it.payload.submit){
          await frappe.call({method:'frappe.client.submit', args:{doc:{doctype:'AlphaX POS Order', name}}});
        }
        ok++;
      }catch(e){ fail++; remaining.push(it); }
    }
    set_queue(remaining); render_queue();
  boot_from_terminal();
    frappe.msgprint(`Sync complete. Success: ${ok}, Failed: ${fail}`);
  }

  async function add_credit_note(){
    const total=ui_total();
    const already=state.payments.filter(p=>p.payment_type==='Credit Note Redeem').reduce((s,p)=>s+(p.amount||0),0);
    const remaining=Math.max(0, total - already);

    const d=new frappe.ui.Dialog({
      title:'Redeem Credit Note',
      fields:[
        {fieldname:'credit_note', label:'Credit Note No (scan or enter)', fieldtype:'Data', reqd:1},
        {fieldname:'amount', label:'Amount', fieldtype:'Currency', reqd:1, read_only:1},
        {fieldname:'allow_edit', label:'Allow edit amount', fieldtype:'Check', default: (state.settings && state.settings.allow_edit_credit_note_amount) ? 1 : 0}
      ],
      primary_action_label:'Add',
      primary_action: async (v)=>{
        const cn=(v.credit_note||'').trim();
        const r=await frappe.call({method:'alphax_pos_suite.alphax_pos_suite.pos.redemption.get_credit_note_available', args:{credit_note: cn}});
        const avail=(r.message && r.message.available) || 0;
        let amt=Math.min(avail, remaining);
        const can_edit = !!(state.settings && state.settings.allow_edit_credit_note_amount) && !!v.allow_edit;
        if(can_edit){ amt = Math.min(parseFloat(v.amount||amt), avail, remaining); }
        state.payments.push({payment_type:'Credit Note Redeem', credit_note: cn, credit_available: avail, amount: amt});
        render_payments(); d.hide();
      }
    });
    d.show();

    d.fields_dict.credit_note.$input.on('keydown', async (e)=>{
      if(e.key!=='Enter') return;
      const cn=d.get_value('credit_note');
      if(!cn) return;
      const r=await frappe.call({method:'alphax_pos_suite.alphax_pos_suite.pos.redemption.get_credit_note_available', args:{credit_note: cn}});
      const avail=(r.message && r.message.available) || 0;
      d.set_value('amount', Math.min(avail, remaining));
      const can_edit = !!(state.settings && state.settings.allow_edit_credit_note_amount) && !!d.get_value('allow_edit');
      d.set_df_property('amount','read_only', can_edit ? 0 : 1);
    });
  }

  // -- Pay by Card (v15.5.16) ---------------------------------------- *
  //
  // Initiates a card-terminal transaction via the backend's
  // request_card_payment endpoint. Shows a modal while waiting for the
  // cardholder to tap/insert. Polls for status every 1.5s until the
  // transaction reaches a final state.
  //
  // On Approval: adds a payment line of type "Card" with the auth
  // details. The cashier still needs to click "Pay & Submit" to
  // complete the sale (intentional — gives them a chance to add cash
  // tip etc. before submitting).
  async function pay_by_card(){
    const terminal = $(wrapper).find('[data-field="terminal"]').val().trim();
    const total = ui_total();
    const already = state.payments.reduce((s,p) => s + (p.amount||0), 0);
    const remaining = Math.max(0, total - already);

    const d = new frappe.ui.Dialog({
      title: 'Pay by Card',
      fields: [
        {fieldname: 'amount', label: 'Amount', fieldtype: 'Currency', default: remaining, reqd: 1,
         description: 'Amount to charge to the card. Defaults to the remaining balance.'},
      ],
      primary_action_label: 'Tap / Insert Card',
      primary_action: async (v) => {
        const amount = parseFloat(v.amount || 0);
        if (!amount || amount <= 0){
          frappe.msgprint('Amount must be greater than 0');
          return;
        }
        d.hide();
        await _run_card_transaction(amount, terminal);
      }
    });
    d.show();
  }

  async function _run_card_transaction(amount, terminal){
    // Generate uuid (crypto.randomUUID is in modern browsers; fall back to a simple generator)
    const uuid = (crypto && crypto.randomUUID) ? crypto.randomUUID()
                 : 'tx-' + Date.now() + '-' + Math.random().toString(36).slice(2, 10);

    // Show a non-dismissable "Waiting for cardholder" dialog
    const waiting = new frappe.ui.Dialog({
      title: '💳 Waiting for cardholder...',
      fields: [
        {fieldtype: 'HTML', fieldname: 'status_html'},
      ],
      primary_action_label: 'Cancel',
      primary_action: async () => {
        try {
          await frappe.call({
            method: 'alphax_pos_suite.alphax_pos_suite.integrations.card_reader.api.cancel_card_payment',
            args: {transaction_uuid: uuid}
          });
        } catch(e){}
        waiting.hide();
        frappe.show_alert({message: 'Card payment cancelled.', indicator: 'orange'}, 4);
      }
    });
    waiting.$wrapper.find('.modal-dialog .close').hide();
    waiting.fields_dict.status_html.$wrapper.html(`
      <div style="text-align:center; padding: 20px;">
        <div style="font-size: 48px; margin-bottom: 12px;">💳</div>
        <div style="font-size: 18px; font-weight: 600; color: var(--alphax-mauve, #714B67); margin-bottom: 8px;">
          Please ask the customer to tap, insert, or swipe their card
        </div>
        <div style="font-size: 14px; color: #666; margin-bottom: 16px;">
          Amount: <b>${amount.toFixed(2)}</b>
        </div>
        <div data-area="poll_status" style="font-size: 13px; color: #888;">Connecting to card reader...</div>
      </div>
    `);
    waiting.show();

    // Kick off the request
    let initiate_result;
    try {
      const r = await frappe.call({
        method: 'alphax_pos_suite.alphax_pos_suite.integrations.card_reader.api.request_card_payment',
        args: {
          transaction_uuid: uuid,
          amount: amount,
          currency: 'SAR',
          alphax_terminal: terminal,
        }
      });
      initiate_result = r.message || {};
    } catch(e){
      waiting.hide();
      frappe.msgprint({
        title: 'Card reader error',
        message: (e && e.message) || 'Failed to reach the card reader.',
        indicator: 'red'
      });
      return;
    }

    if (!initiate_result.ok){
      waiting.hide();
      frappe.msgprint({
        title: 'Card payment failed',
        message: initiate_result.error || 'Unknown error.',
        indicator: 'red'
      });
      return;
    }

    // Poll for status. Maximum 90 seconds (60s configured + buffer).
    waiting.fields_dict.status_html.$wrapper.find('[data-area="poll_status"]')
      .text('Waiting for response from card reader...');

    const startTime = Date.now();
    const maxWaitMs = 90 * 1000;
    let lastStatus = 'Pending';

    while (Date.now() - startTime < maxWaitMs) {
      await new Promise(resolve => setTimeout(resolve, 1500));
      try {
        const r = await frappe.call({
          method: 'alphax_pos_suite.alphax_pos_suite.integrations.card_reader.api.get_card_payment_status',
          args: {transaction_uuid: uuid}
        });
        const status = (r.message && r.message.status) || 'Pending';
        lastStatus = status;
        if (status !== 'Pending') {
          waiting.hide();
          if (status === 'Approved') {
            // Add a card payment line
            state.payments.push({
              payment_type: 'Payment',
              mode_of_payment: 'Card',  // generic; vendor-specific MoP can be configured
              amount: amount,
              card_transaction: r.message.transaction,
              auth_code: r.message.auth_code,
              card_brand: r.message.card_brand,
              masked_pan: r.message.masked_pan,
              rrn: r.message.rrn,
            });
            render_payments();
            frappe.show_alert({
              message: `✓ Card approved. ${r.message.card_brand || ''} ${r.message.masked_pan || ''}`,
              indicator: 'green'
            }, 6);
          } else {
            // Declined / Error / Timeout / Cancelled
            const indicator = status === 'Declined' ? 'red' : 'orange';
            frappe.msgprint({
              title: `Card payment ${status.toLowerCase()}`,
              message: (r.message.response_message || '') +
                       (r.message.response_code ? ` (Code: ${r.message.response_code})` : ''),
              indicator: indicator
            });
          }
          return;
        }
      } catch(e){
        // Poll failed - continue trying
      }
    }

    // Hit the max wait
    waiting.hide();
    frappe.msgprint({
      title: 'Card reader timeout',
      message: 'No response from the card reader in 90 seconds. ' +
               'The transaction may still complete on the reader; check the audit log.',
      indicator: 'orange'
    });
  }

  function add_payment(){
    const mop=$(wrapper).find('[data-field="mop"]').val().trim();
    const amt=parseFloat($(wrapper).find('[data-field="amt"]').val()||0);
    if(!mop || !amt) return frappe.msgprint('Enter Mode of Payment and Amount');
    state.payments.push({payment_type:'Payment', mode_of_payment:mop, amount:amt});
    $(wrapper).find('[data-field="mop"]').val('');
    $(wrapper).find('[data-field="amt"]').val('');
    render_payments();
  }

  // -- Receipt printing (v15.5.16) ------------------------------------- *
  //
  // Looks up a Printer Profile for the current terminal and dispatches
  // the receipt via window.AlphaXPrint. AlphaXPrint handles transport
  // (qz-tray if installed, browser dialog otherwise) — we just provide
  // the content.
  //
  // The receipt body is built from the order doc (already-submitted),
  // formatted as ESC/POS plain text. Width and encoding come from the
  // Printer Profile.
  async function _print_receipt_for_order(order_name, order_doc) {
    const terminal = $(wrapper).find('[data-field="terminal"]').val().trim();
    if (!terminal) return;  // no terminal → nothing to print to

    // Look up the printer profile for this terminal. Best-effort: if
    // none is configured, we silently skip printing — managers can
    // configure profiles later via the doctype list.
    let profile = null;
    try {
      const r = await frappe.call({
        method: 'frappe.client.get_list',
        args: {
          doctype: 'AlphaX POS Printer Profile',
          filters: { is_active: 1, alphax_terminal: terminal },
          fields: ['name', 'transport', 'qz_printer_name', 'paper_width_mm',
                   'characters_per_line', 'encoding', 'auto_cut',
                   'open_cash_drawer', 'print_format', 'letterhead'],
          limit_page_length: 1,
        }
      });
      profile = (r.message && r.message[0]) || null;
    } catch(e){
      // List call failed (doctype not yet migrated, permissions, etc.) — skip silently
      return;
    }
    if (!profile) return;

    // Build a simple ESC/POS receipt body. For v15.5.16 we build it
    // client-side from the current order state. Server-side rendering
    // via the linked Print Format is a v15.5.17+ enhancement.
    const helpers = window.AlphaXPrint.escposHelpers;
    const width = profile.characters_per_line || 42;
    const lines = [];

    // Header — company / outlet name centered
    const station_banner = $(wrapper).find('[data-area="station_banner"]').text().trim() || 'AlphaX POS';
    lines.push(helpers.center(helpers.bold(station_banner.substring(0, width))));
    lines.push(helpers.line('-', width));

    // Order number, date, customer
    lines.push(`Order: ${order_name}`);
    lines.push(`Date:  ${frappe.datetime.now_datetime()}`);
    const customer = $(wrapper).find('[data-field="customer"]').val().trim();
    if (customer) lines.push(`Cust:  ${customer}`);
    lines.push(helpers.line('-', width));

    // Items
    for (const it of (order_doc.items || [])) {
      const name_part = String(it.item_code || '').padEnd(width - 14).substring(0, width - 14);
      const qty_part = String(it.qty).padStart(4);
      const total_part = (parseFloat(it.qty || 0) * parseFloat(it.rate || 0))
                          .toFixed(2).padStart(9);
      lines.push(name_part + qty_part + total_part);
    }
    lines.push(helpers.line('-', width));

    // Total
    const total = ui_total();
    const total_label = 'TOTAL'.padEnd(width - 10);
    lines.push(helpers.bold(total_label + total.toFixed(2).padStart(10)));

    // Payments
    for (const p of (order_doc.payments || [])) {
      const label = (p.payment_type === 'Credit Note Redeem'
                     ? `Credit Note ${p.credit_note || ''}`
                     : (p.mode_of_payment || 'Payment')).padEnd(width - 10);
      lines.push(label + parseFloat(p.amount || 0).toFixed(2).padStart(10));
    }
    lines.push(helpers.line('-', width));
    lines.push(helpers.center('Thank you for your visit'));
    lines.push(helpers.feed(2));

    // Build HTML fallback for browser dialog mode
    const html = '<pre>' + lines.join('\n')
                  .replace(/[\x1B\x1D][^]/g, '')  // strip ESC/POS for HTML preview
                  + '</pre>';

    await window.AlphaXPrint.printReceipt({
      html: html,
      escposLines: lines,
      printerName: profile.qz_printer_name,
      autoCut: !!profile.auto_cut,
      openDrawer: !!profile.open_cash_drawer,
      encoding: profile.encoding || 'UTF-8',
      charsPerLine: width,
    });
  }

  async function create_order({hold=false, submit=false, is_return=false}){
    const terminal=$(wrapper).find('[data-field="terminal"]').val().trim();
    const customer=$(wrapper).find('[data-field="customer"]').val().trim();
    const offer=$(wrapper).find('[data-field="offer_code"]').val().trim();
    if(!terminal) return frappe.msgprint('Terminal is required');
    if(!customer) return frappe.msgprint('Customer is required');
    if(!state.cart.length) return frappe.msgprint('Add at least one item');

    let return_against=null, return_reason=null;
    if(is_return){
      const v=await new Promise(resolve=>{
        const d=new frappe.ui.Dialog({
          title:'Return Invoice',
          fields:[
            {fieldname:'return_against', label:'Return Against Invoice (scan or enter)', fieldtype:'Data', reqd:1},
            {fieldname:'return_reason', label:'Return Reason', fieldtype:'Link', options:'AlphaX POS Return Reason'}
          ],
          primary_action_label:'Continue',
          primary_action:(vals)=>{ d.hide(); resolve(vals); }
        });
        d.show();
      });
      return_against=v.return_against;
      return_reason=v.return_reason;
    }

    const doc={
      doctype:'AlphaX POS Order',
      client_uuid: frappe.utils.get_random(20),
      client_device: navigator.userAgent,
      pos_terminal: terminal,
      customer: customer,
      posting_date: frappe.datetime.nowdate(),
      posting_time: frappe.datetime.now_time(),
      order_status: hold ? 'Hold' : 'Active',
      offer_code: offer,
      is_return: is_return ? 1 : 0,
      return_against: return_against,
      return_reason: return_reason,
      items: state.cart.map(r=>({doctype:'AlphaX POS Order Item', item_code:r.item_code, qty:r.qty, rate:r.rate})),
      payments: state.payments.map(p=>{
        if(p.payment_type==='Credit Note Redeem') return {doctype:'AlphaX POS Payment', payment_type:'Credit Note Redeem', credit_note:p.credit_note, amount:p.amount};
        return {doctype:'AlphaX POS Payment', payment_type:'Payment', mode_of_payment:p.mode_of_payment, amount:p.amount};
      })
    };

    try{
      const ins=await frappe.call({method:'frappe.client.insert', args:{doc}});
      const name=ins.message.name;
      if(submit && !hold){
        await frappe.call({method:'frappe.client.submit', args:{doc:{doctype:'AlphaX POS Order', name}}});
        frappe.msgprint(`Submitted POS Order ${name}`);

        // v15.5.16 — auto-print the receipt via AlphaXPrint.
        // Quiet failure: a print problem must NEVER block the next sale.
        // The receipt can always be reprinted from the order's list view.
        try {
          if (window.AlphaXPrint) {
            await _print_receipt_for_order(name, doc);
          }
        } catch(e){
          console.warn('Auto-print failed (non-fatal):', e);
        }
      } else {
        frappe.msgprint(`Saved POS Order ${name}`);
      }
      state.cart=[]; state.payments=[];
      render_cart(); render_payments(); refresh_holds();
    }catch(e){
      queue_push({doc, submit: submit && !hold});
      render_queue();
      frappe.msgprint('Posting failed. Saved to offline queue.');
    }
  }

  $(wrapper).on('keydown','[data-field="scan"]', async (e)=>{ if(e.key==='Enter') await add_item(); });
  $(wrapper).on('click','[data-action="add_item"]', add_item);
  $(wrapper).on('click','[data-action="inc"]', function(){ const i=parseInt($(this).attr('data-idx')); state.cart[i].qty+=1; render_cart(); });
  $(wrapper).on('click','[data-action="dec"]', function(){ const i=parseInt($(this).attr('data-idx')); state.cart[i].qty=Math.max(1,state.cart[i].qty-1); render_cart(); });
  $(wrapper).on('click','[data-action="rm"]', function(){ const i=parseInt($(this).attr('data-idx')); state.cart.splice(i,1); render_cart(); });

  $(wrapper).on('click','[data-action="add_payment"]', add_payment);
  $(wrapper).on('click','[data-action="rm_pay"]', function(){ const i=parseInt($(this).attr('data-idx')); state.payments.splice(i,1); render_payments(); });
  $(wrapper).on('click','[data-action="add_credit_note"]', add_credit_note);
  $(wrapper).on('click','[data-action="pay_by_card"]', pay_by_card);

  $(wrapper).on('click','[data-action="hold"]', ()=>create_order({hold:true, submit:false}));
  $(wrapper).on('click','[data-action="submit"]', ()=>create_order({hold:false, submit:true}));
  $(wrapper).on('click','[data-action="return"]', ()=>create_order({hold:false, submit:true, is_return:true}));

  $(wrapper).on('click','[data-action="refresh_holds"]', refresh_holds);
  $(wrapper).on('click','[data-action="show_queue"]', render_queue);
  $(wrapper).on('click','[data-action="clear_queue"]', ()=>{ set_queue([]); render_queue(); });
  $(wrapper).on('click','[data-action="sync_queue"]', sync_queue);

  $(wrapper).on('click','[data-action="shift_list"]', ()=>frappe.set_route('List','AlphaX POS Shift'));
  $(wrapper).on('click','[data-action="cash_moves"]', ()=>frappe.set_route('List','AlphaX POS Cash Movement'));

  async function boot_from_terminal(){
    const terminal = $(wrapper).find('[data-field="terminal"]').val().trim();
    if(!terminal) return;
    try{
        const r = await frappe.call({method:'alphax_pos_suite.alphax_pos_suite.api.get_pos_boot', args:{terminal}});
        const boot = r.message || {};
        state.boot = boot;
        state.profile = boot.profile || {};
        state.theme = boot.theme || null;
        state.allowed_mops = boot.payment_methods || [];
        state.scale = boot.scale || {generic:null, prefix_map:[]};
        apply_theme(state.theme);
        await load_mops();
        render_mop_tiles();
    }catch(e){
        // ignore
    }
}

load_settings(); load_mops(); render_cart(); render_payments(); refresh_holds(); render_queue();

// ---------------------------------------------------------------------- *
// Terminal binding (v15.5.13)
// ---------------------------------------------------------------------- *
//
// PCs are physically bound to a terminal. The binding lives in this
// browser's localStorage. Once set, neither the cashier nor casual
// users can change it — only a manager can, by typing their username
// and PIN. This is checked server-side via the verify_manager_pin
// endpoint, which has its own lockout and audit logic.
//
// Resolution flow on page load:
//
//   1. Read terminal from localStorage.
//   2. If found and the terminal still exists server-side: load the
//      cashier UI normally.
//   3. If found but the terminal was deleted server-side: clear
//      localStorage, fall through to step 4.
//   4. If not found: hide the cashier UI, show the "Station Not
//      Configured" card. Cashier cannot take orders until a manager
//      authorizes binding via the PIN dialog.
//
// The gear (⚙) icon at top-right is always visible. Clicking it opens
// the PIN dialog regardless of station state, so a manager can
// re-bind, change, or reset the station at any time.

const TERMINAL_LS_KEY = 'alphax_pos_classic_terminal_v1';

function pc_terminal(){
  try { return localStorage.getItem(TERMINAL_LS_KEY) || null; }
  catch(e){ return null; }
}
function set_pc_terminal(t){
  try {
    if (t) localStorage.setItem(TERMINAL_LS_KEY, t);
    else localStorage.removeItem(TERMINAL_LS_KEY);
  } catch(e){}
}

async function update_station_banner(terminal){
  const $value = $(wrapper).find('[data-area="station_value"]');
  if (!terminal){
    $value.html('<span class="alphax-station-empty">Not configured</span>');
    return;
  }
  try {
    const t = await frappe.db.get_value('AlphaX POS Terminal', terminal, ['pos_outlet']);
    const outlet = (t && t.message && t.message.pos_outlet) || null;
    let outlet_name = outlet, branch = '';
    if (outlet) {
      const o = await frappe.db.get_value('AlphaX POS Outlet', outlet, ['outlet_name', 'branch']);
      if (o && o.message){
        outlet_name = o.message.outlet_name || outlet;
        branch = o.message.branch || '';
      }
    }
    const parts = [];
    if (branch) parts.push(`<b>${frappe.utils.escape_html(branch)}</b>`);
    if (outlet_name) parts.push(frappe.utils.escape_html(outlet_name));
    parts.push(`Terminal <b>${frappe.utils.escape_html(terminal)}</b>`);
    $value.html(parts.join(' <span class="alphax-station-sep">›</span> '));
  } catch(e) {
    $value.html(`Terminal <b>${frappe.utils.escape_html(terminal)}</b>`);
  }
}

function show_cashier_ui(){
  $(wrapper).find('[data-area="not_configured"]').hide();
  $(wrapper).find('[data-area="cashier_ui"]').show();
}
function show_not_configured(){
  $(wrapper).find('[data-area="cashier_ui"]').hide();
  $(wrapper).find('[data-area="not_configured"]').show();
  update_station_banner(null);
}

async function bind_terminal(terminal){
  if (!terminal){
    set_pc_terminal(null);
    show_not_configured();
    return;
  }
  set_pc_terminal(terminal);
  $(wrapper).find('[data-field="terminal"]').val(terminal)
    .attr('readonly', true).addClass('alphax-input-locked');
  await update_station_banner(terminal);
  show_cashier_ui();
  boot_from_terminal();

  // v15.5.15: resolve which POS Profile applies for this user × terminal
  try {
    const r = await frappe.call({
      method: 'alphax_pos_suite.alphax_pos_suite.boot.api.resolve_session_pos_profile',
      args: { terminal }
    });
    const m = r.message || {};
    if (m.profile){
      // Quietly set a global so other code can read the active profile.
      // The "profile picker when multiple candidates" UI is v15.5.16+.
      window.__alphax_active_profile = m.profile;
      if (m.needs_picker && m.candidates.length > 1){
        frappe.show_alert({
          message: `${m.candidates.length} POS Profiles available. Active: ${m.profile}.`,
          indicator: 'blue'
        }, 5);
      }
    } else if (m.message){
      frappe.msgprint({
        title: 'No POS Profile',
        message: m.message,
        indicator: 'orange'
      });
    }
  } catch(e){
    // Profile resolution failed — non-fatal, the cashier still loads.
    // boot_from_terminal() already pulled a profile via the legacy path.
  }
}

// ---------------------------------------------------------------------- *
// Manager PIN dialog
// ---------------------------------------------------------------------- *
// One unified dialog that:
//   1. Asks for manager username + PIN
//   2. On verification success, presents the post-auth menu
//      (Bind/Change Terminal, Reset Station)
//   3. On failure, shows the error inline and lets the user retry
//
// We never auto-fill the username (no leakage about valid managers)
// and never store credentials anywhere client-side.

function open_manager_dialog(){
  let stage = 'auth';     // 'auth' | 'menu'
  let manager_name = '';

  const d = new frappe.ui.Dialog({
    title: 'Manager Setup',
    fields: [
      { fieldtype: 'HTML', fieldname: 'header_html' },
      { fieldtype: 'Data', fieldname: 'manager_user', label: 'Manager Username',
        description: 'Your Frappe username (usually your email).' },
      { fieldtype: 'Password', fieldname: 'manager_pin', label: 'Manager PIN' },
      { fieldtype: 'HTML', fieldname: 'error_html' },
      { fieldtype: 'HTML', fieldname: 'menu_html' },
    ],
    primary_action_label: 'Verify',
    primary_action: async (vals) => {
      if (stage !== 'auth') return;
      const user = (vals.manager_user || '').trim();
      const pin = (vals.manager_pin || '').trim();
      if (!user || !pin){
        d.fields_dict.error_html.$wrapper.html(
          `<div class="alphax-dialog-error">Both username and PIN are required.</div>`
        );
        return;
      }

      d.fields_dict.error_html.$wrapper.html(
        `<div class="alphax-dialog-info">Verifying…</div>`
      );
      d.set_primary_action('Verify', null);  // disable while in flight

      try {
        const r = await frappe.call({
          method: 'alphax_pos_suite.alphax_pos_suite.security.manager_pin.verify_manager_pin',
          args: {
            user, pin,
            action_type: 'Verify Only',
            terminal: pc_terminal() || '',
          }
        });
        const result = r.message || {};
        if (result.authorized){
          stage = 'menu';
          manager_name = result.manager_name || user;
          d.set_df_property('manager_user', 'hidden', 1);
          d.set_df_property('manager_pin', 'hidden', 1);
          d.fields_dict.error_html.$wrapper.html('');
          d.fields_dict.menu_html.$wrapper.html(`
            <div class="alphax-dialog-success">
              ✓ Authorized as <b>${frappe.utils.escape_html(manager_name)}</b>
            </div>
            <div class="alphax-dialog-menu">
              <button class="alphax-btn alphax-btn-primary alphax-btn-block" data-mgr-action="bind">
                ${pc_terminal() ? 'Change Terminal' : 'Bind This PC to a Terminal'}
              </button>
              ${pc_terminal() ? `
                <button class="alphax-btn alphax-btn-danger alphax-btn-block" data-mgr-action="reset">
                  Reset Station (Clear Binding)
                </button>` : ''}
            </div>
          `);
          d.fields_dict.menu_html.$wrapper.find('[data-mgr-action="bind"]').on('click', async () => {
            d.hide();
            await open_terminal_picker(manager_name);
          });
          d.fields_dict.menu_html.$wrapper.find('[data-mgr-action="reset"]').on('click', () => {
            d.hide();
            confirm_reset_station(manager_name);
          });
          d.set_primary_action('Done', () => d.hide());
        } else {
          // Failure — show inline error, keep the dialog open
          let errMsg = result.message || 'Verification failed.';
          if (result.locked_until){
            errMsg += ` (Locked until ${result.locked_until})`;
          }
          d.fields_dict.error_html.$wrapper.html(
            `<div class="alphax-dialog-error">${frappe.utils.escape_html(errMsg)}</div>`
          );
          d.fields_dict.manager_pin.$input.val('').focus();
          d.set_primary_action('Verify', d.primary_action);
        }
      } catch(e){
        d.fields_dict.error_html.$wrapper.html(
          `<div class="alphax-dialog-error">Network error. Please try again.</div>`
        );
        d.set_primary_action('Verify', d.primary_action);
      }
    },
  });

  d.fields_dict.header_html.$wrapper.html(`
    <div class="alphax-dialog-header">
      Manager credentials are required to bind, change, or reset this PC's terminal.
    </div>
  `);
  d.show();
  setTimeout(() => d.fields_dict.manager_user.$input.focus(), 100);
}

async function open_terminal_picker(manager_name){
  let rows = [];
  try {
    const r = await frappe.call({
      method: 'alphax_pos_suite.alphax_pos_suite.boot.api.list_terminals_for_picker'
    });
    rows = r.message || [];
  } catch(e){ rows = []; }

  if (!rows.length){
    frappe.msgprint({
      title: 'No Terminals Available',
      message: 'No AlphaX POS Terminals have been created yet. A System Manager must create at least one terminal before any PC can be bound.',
      indicator: 'orange'
    });
    return;
  }

  const options = rows.map(r => {
    const parts = [];
    if (r.branch) parts.push(r.branch);
    if (r.outlet_name) parts.push(r.outlet_name);
    parts.push(`Terminal ${r.terminal}`);
    return { value: r.terminal, label: parts.join(' › ') };
  });

  const d = new frappe.ui.Dialog({
    title: 'Bind PC to Terminal',
    fields: [
      { fieldtype: 'HTML', fieldname: 'header_html' },
      {
        fieldtype: 'Select', fieldname: 'terminal', label: 'Terminal',
        options: options.map(o => o.label).join('\n'), reqd: 1,
        description: 'Once bound, this PC will use the selected terminal until a manager re-binds or resets it.'
      }
    ],
    primary_action_label: 'Bind This PC',
    primary_action: async (vals) => {
      const chosen = options.find(o => o.label === vals.terminal);
      if (!chosen){ d.hide(); return; }
      // Notify the audit log of the bind action (a successful PIN
      // already happened to open this dialog; this records what the
      // manager did with that authorization).
      try {
        await frappe.call({
          method: 'alphax_pos_suite.alphax_pos_suite.security.manager_pin.log_action',
          args: {
            action_type: pc_terminal() ? 'Change Terminal' : 'Bind Terminal',
            terminal: chosen.value,
          }
        });
      } catch(e){ /* audit failure must not block the action */ }
      d.hide();
      await bind_terminal(chosen.value);
      frappe.show_alert({
        message: `This PC is now bound to ${frappe.utils.escape_html(chosen.label)}`,
        indicator: 'green'
      }, 5);
    }
  });
  d.fields_dict.header_html.$wrapper.html(`
    <div class="alphax-dialog-header">
      Authorized as <b>${frappe.utils.escape_html(manager_name)}</b>.
      Pick the terminal this PC should use.
    </div>
  `);
  d.show();
}

function confirm_reset_station(manager_name){
  frappe.confirm(
    `Reset this station and clear its terminal binding?<br><br>` +
    `Authorized by <b>${frappe.utils.escape_html(manager_name)}</b>.<br>` +
    `After reset, this PC will need to be bound again before it can take orders.`,
    async () => {
      try {
        await frappe.call({
          method: 'alphax_pos_suite.alphax_pos_suite.security.manager_pin.log_action',
          args: { action_type: 'Reset Station', terminal: pc_terminal() || '' }
        });
      } catch(e){}
      bind_terminal(null);
      frappe.show_alert({ message: 'Station has been reset.', indicator: 'orange' }, 5);
    }
  );
}

// Top-bar gear icon and the "Manager Setup" button on the
// not-configured card both point to the same action.
$(wrapper).on('click', '[data-action="manager_setup"]', open_manager_dialog);

async function resolve_terminal_on_load(){
  const pc = pc_terminal();
  if (pc){
    try {
      const exists = await frappe.db.exists('AlphaX POS Terminal', pc);
      if (exists){
        await bind_terminal(pc);  // shows cashier UI
        return;
      }
      // Stale localStorage — server-side terminal was deleted
      set_pc_terminal(null);
    } catch(e){ /* fall through */ }
  }
  show_not_configured();
}

resolve_terminal_on_load();

// When the user navigates away, remove the body class so the cashier
// theme doesn't leak onto other pages.
frappe.router.on('change', function cleanup(){
    if (frappe.get_route_str().indexOf('alphax-pos-classic') === -1) {
        $('body').removeClass('alphax-pos-classic-page');
        frappe.router.off('change', cleanup);
    }
});
};
