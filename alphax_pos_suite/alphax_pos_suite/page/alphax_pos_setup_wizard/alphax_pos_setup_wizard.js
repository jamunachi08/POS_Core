/*
 * AlphaX POS Setup Wizard
 *
 * 5-step guided setup that takes a fresh install from "nothing" to
 * "ready to take sales" in under 10 minutes.
 *
 * Steps:
 *   1. Company basics (name, VAT, currency, country)
 *   2. First branch (name, address)
 *   3. First outlet + business type (picks domain pack)
 *   4. First terminal (this PC) + binding
 *   5. Admin user + manager PIN
 *
 * Each step has a side panel explaining WHY we're asking. This makes
 * the wizard feel professional rather than bureaucratic — the user
 * understands what each piece does, not just what it's named.
 *
 * On the final step, all records are created in a single backend
 * transaction (rolls back if any step fails). The user lands directly
 * on the cashier with everything wired up.
 */
frappe.pages['alphax-pos-setup-wizard'].on_page_load = function(wrapper) {
  frappe.ui.make_app_page({
    parent: wrapper,
    title: 'AlphaX POS Setup',
    single_column: true
  });

  $('body').addClass('alphax-pos-wizard-page');

  // Wizard state — collected across all steps, sent in one backend call
  // at the end. Nothing is persisted server-side until step 5's submit.
  const state = {
    step: 1,
    company: { name: '', vat: '', currency: 'SAR', country: 'Saudi Arabia', existing: '', mode: '' },
    branch: { name: '', address: '', existing: '', mode: '' },
    outlet: { name: '', domain: 'Generic' },
    terminal: { name: 'Terminal 1', pc_hostname: '' },
    admin: { full_name: '', email: '', pin: '' },
  };

  // Existing site data (companies / branches) loaded at mount so the user
  // can SELECT what already exists instead of creating duplicates.
  let ctx = { companies: [], branches: [] };

  // The 10 business types presented to the user. Each maps to a
  // Domain Pack. The "tagline" appears under the radio button.
  const BUSINESS_TYPES = [
    { code: 'Cafe',         label: 'Coffee Shop',          tagline: 'Drinks, light food, modifiers, kitchen tickets', icon: '☕' },
    { code: 'Restaurant',   label: 'Restaurant',           tagline: 'Tables, courses, KDS, split bills', icon: '🍽' },
    { code: 'Pharmacy',     label: 'Pharmacy',             tagline: 'Drug master, prescriptions, batch & expiry', icon: '💊' },
    { code: 'Supermarket',  label: 'Supermarket',          tagline: 'Weighing scale, multi-pack, batch tracking', icon: '🛒' },
    { code: 'Retail',       label: 'Retail Store',         tagline: 'Standard cart, serial capture, loyalty', icon: '🏬' },
    { code: 'Bakery',       label: 'Bakery',               tagline: 'Recipes, batch baking, weighing', icon: '🥖' },
    { code: 'Clothing',     label: 'Clothing & Apparel',   tagline: 'Sizes, colors, simple cart', icon: '👕' },
    { code: 'Electronics',  label: 'Electronics',          tagline: 'Serial numbers, warranty registration', icon: '📱' },
    { code: 'Garage',       label: 'Auto Service Shop',    tagline: 'Appointments, service items, parts', icon: '🔧' },
    { code: 'Generic',      label: 'Other / Generic',      tagline: 'I\'ll configure features myself later', icon: '📦' },
  ];

  // Per-step explainer text (the side panel). Plain language —
  // a non-technical owner reads this and understands why we ask.
  const EXPLAINERS = {
    1: {
      title: 'About your company',
      body: `Your <b>company</b> is the legal entity that owns the shop. It's what
             goes on your tax returns and on every customer receipt.<br><br>
             For Saudi Arabia, your <b>VAT number</b> is the 15-digit ID
             from ZATCA. We use it to submit invoices automatically.<br><br>
             <b>Currency</b> is what you sell in. Default SAR for KSA;
             change if you operate elsewhere.<br><br>
             <span class="alphax-wiz-hint">You can add more companies later from the Frappe sidebar
             if you grow into a multi-entity group.</span>`
    },
    2: {
      title: 'About your first branch',
      body: `A <b>branch</b> is a physical location — one shop at one address.
             A multi-shop business has multiple branches, but you can start
             with just one. Add more later from the Branch list.<br><br>
             The <b>address</b> appears on every receipt and is required
             for ZATCA Phase 2 e-invoicing in Saudi Arabia.<br><br>
             <span class="alphax-wiz-hint">Tip: use a name your staff will recognize, like
             "Riyadh Mall - Main" or "Jeddah Souq Branch". Internal
             code is fine too.</span>`
    },
    3: {
      title: 'About your business type',
      body: `Your <b>business type</b> tells us which features to turn on.
             A pharmacy needs prescription handling; a coffee shop needs
             modifiers (size, milk, sweetness); a clothing store doesn't
             need either.<br><br>
             We call these <b>domain packs</b>. Pick what fits best — you
             can always add more outlets with different types later
             (e.g. a coffee shop and a pharmacy at the same mall).<br><br>
             <span class="alphax-wiz-hint">Not sure? "Other / Generic" is a safe pick.
             You can change this on the Outlet record any time.</span>`
    },
    4: {
      title: 'About this cashier station',
      body: `A <b>terminal</b> represents one physical cashier station —
             usually one PC at a counter. We're going to bind <i>this
             PC</i> (the one you're using right now) to a terminal record
             so it remembers its station forever.<br><br>
             The <b>terminal name</b> is just a short label —
             "Terminal 1", "A07", "Front Counter" — whatever you'll
             call it when telling staff "Mohammed, you're on Terminal 1
             today."<br><br>
             <span class="alphax-wiz-hint">After setup, this PC opens straight to the cashier
             register. No re-binding needed unless the PC changes
             location.</span>`
    },
    5: {
      title: 'About the admin user',
      body: `The <b>admin user</b> is you (or whoever runs this shop).
             You'll log in with this email and a password we'll send
             you. As admin, you have full access.<br><br>
             The <b>manager PIN</b> is a 4-6 digit number you'll use at
             the cashier counter to authorize things like discounts,
             returns, or station re-binding. PINs are bcrypt-hashed
             and never visible in the database.<br><br>
             You can add more cashier and manager accounts later from
             the Users list.<br><br>
             <span class="alphax-wiz-hint">Pick a PIN you'll remember but isn't obvious. Avoid
             1234, 0000, or your birth year.</span>`
    },
  };

  // Render the wizard shell — header with progress, two-column body
  // (form left, explainer right), footer with prev/next buttons.
  const $root = $(wrapper).find('.layout-main-section');
  $root.html(`
    <div class="alphax-wiz-shell">
      <div class="alphax-wiz-header">
        <h1>Set up your AlphaX POS</h1>
        <div class="alphax-wiz-subtitle">5 quick questions, then you're ready to take sales.</div>
        <div class="alphax-wiz-progress" data-area="progress"></div>
      </div>

      <div class="alphax-wiz-body">
        <div class="alphax-wiz-form" data-area="form"></div>
        <div class="alphax-wiz-side" data-area="side"></div>
      </div>

      <div class="alphax-wiz-footer">
        <button class="alphax-btn alphax-btn-ghost" data-action="prev">← Back</button>
        <div class="alphax-wiz-step-indicator" data-area="step_indicator"></div>
        <button class="alphax-btn alphax-btn-primary alphax-btn-pay" data-action="next">Next →</button>
      </div>
    </div>
  `);

  function render_progress(){
    const $p = $(wrapper).find('[data-area="progress"]');
    let html = '<div class="alphax-wiz-steps">';
    for (let i = 1; i <= 5; i++){
      const cls = i < state.step ? 'done' : (i === state.step ? 'active' : 'upcoming');
      html += `<div class="alphax-wiz-step ${cls}">
                 <div class="alphax-wiz-step-num">${i < state.step ? '✓' : i}</div>
                 <div class="alphax-wiz-step-label">${stepLabel(i)}</div>
               </div>`;
      if (i < 5) html += '<div class="alphax-wiz-step-line"></div>';
    }
    html += '</div>';
    $p.html(html);
    $(wrapper).find('[data-area="step_indicator"]').text(`Step ${state.step} of 5`);
  }

  function stepLabel(n){
    return ['Company', 'Branch', 'Type', 'Terminal', 'Admin'][n - 1];
  }

  function render_side(){
    const e = EXPLAINERS[state.step];
    $(wrapper).find('[data-area="side"]').html(`
      <div class="alphax-wiz-explainer">
        <div class="alphax-wiz-explainer-icon">💡</div>
        <h3>${e.title}</h3>
        <p>${e.body}</p>
      </div>
    `);
  }

  function render_step(){
    render_progress();
    render_side();

    const $form = $(wrapper).find('[data-area="form"]');
    let html = '';
    if (state.step === 1){
      const companies = (ctx.companies || []);
      const hasCompanies = companies.length > 0;
      const mode = state.company.mode || (hasCompanies ? 'existing' : 'new');
      const showNew = (mode === 'new') || !hasCompanies;
      let pick = '';
      if (hasCompanies){
        pick = `
        <div class="alphax-wiz-field">
          <label>Company <span class="alphax-req">*</span></label>
          <select class="alphax-input" data-field="company_select">
            ${companies.map(c =>
              `<option value="${esc(c.name)}" ${(mode==='existing' && state.company.existing===c.name)?'selected':''}>${esc(c.name)}${c.default_currency?(' · '+esc(c.default_currency)):''}</option>`
            ).join('')}
            <option value="__new__" ${mode==='new'?'selected':''}>➕ Create a new company…</option>
          </select>
          <small>Pick the company you already use, or create a new one.</small>
        </div>`;
      }
      html = `
        <h2>Tell us about your company</h2>
        ${pick}
        <div data-area="new_company" style="${showNew?'':'display:none'}">
        <div class="alphax-wiz-field">
          <label>Company Name <span class="alphax-req">*</span></label>
          <input class="alphax-input" data-field="company_name" value="${esc(state.company.name)}" placeholder="e.g. Neotec Trading Co." ${showNew?'autofocus':''}/>
          <small>The legal name on your tax returns and receipts.</small>
        </div>
        <div class="alphax-wiz-field">
          <label>VAT / Tax ID</label>
          <input class="alphax-input" data-field="company_vat" value="${esc(state.company.vat)}" placeholder="15 digits, e.g. 300012345678003"/>
          <small>Required for KSA. Leave blank if you're not VAT-registered.</small>
        </div>
        <div class="alphax-wiz-row">
          <div class="alphax-wiz-field">
            <label>Currency</label>
            <select class="alphax-input" data-field="company_currency">
              ${['SAR','AED','USD','EUR','GBP','EGP','JOD'].map(c =>
                `<option value="${c}" ${state.company.currency===c?'selected':''}>${c}</option>`
              ).join('')}
            </select>
          </div>
          <div class="alphax-wiz-field">
            <label>Country</label>
            <select class="alphax-input" data-field="company_country">
              ${['Saudi Arabia','United Arab Emirates','Egypt','Jordan','Kuwait','Bahrain','Qatar','Oman','Other'].map(c =>
                `<option value="${c}" ${state.company.country===c?'selected':''}>${c}</option>`
              ).join('')}
            </select>
          </div>
        </div>
        </div>`;
    }
    else if (state.step === 2){
      const branches = (ctx.branches || []);
      const hasBranches = branches.length > 0;
      const mode = state.branch.mode || (hasBranches ? 'existing' : 'new');
      const showNew = (mode === 'new') || !hasBranches;
      let pick = '';
      if (hasBranches){
        pick = `
        <div class="alphax-wiz-field">
          <label>Branch <span class="alphax-req">*</span></label>
          <select class="alphax-input" data-field="branch_select">
            ${branches.map(b =>
              `<option value="${esc(b)}" ${(mode==='existing' && state.branch.existing===b)?'selected':''}>${esc(b)}</option>`
            ).join('')}
            <option value="__new__" ${mode==='new'?'selected':''}>➕ Create a new branch…</option>
          </select>
          <small>Choose an existing ERPNext branch, or create a new one.</small>
        </div>`;
      }
      html = `
        <h2>Your branch</h2>
        ${pick}
        <div data-area="new_branch" style="${showNew?'':'display:none'}">
        <div class="alphax-wiz-field">
          <label>Branch Name <span class="alphax-req">*</span></label>
          <input class="alphax-input" data-field="branch_name" value="${esc(state.branch.name)}" placeholder="e.g. Riyadh Mall - Main" ${showNew?'autofocus':''}/>
          <small>A short label your staff will recognize.</small>
        </div>
        <div class="alphax-wiz-field">
          <label>Address</label>
          <textarea class="alphax-input" data-field="branch_address" rows="3" placeholder="Street, district, city, postal code">${esc(state.branch.address)}</textarea>
          <small>Appears on receipts and is required for ZATCA e-invoicing.</small>
        </div>
        </div>`;
    }
    else if (state.step === 3){
      html = `
        <h2>What kind of business is this?</h2>
        <div class="alphax-wiz-field">
          <label>First outlet name <span class="alphax-req">*</span></label>
          <input class="alphax-input" data-field="outlet_name" value="${esc(state.outlet.name)}" placeholder="e.g. Coffee Counter" autofocus/>
          <small>What you call this section internally. A branch can have several outlets later.</small>
        </div>
        <div class="alphax-wiz-field">
          <label>Business type</label>
          <div class="alphax-wiz-types">
            ${BUSINESS_TYPES.map(t => `
              <label class="alphax-wiz-type ${state.outlet.domain===t.code?'selected':''}">
                <input type="radio" name="domain" value="${t.code}" ${state.outlet.domain===t.code?'checked':''}/>
                <div class="alphax-wiz-type-icon">${t.icon}</div>
                <div class="alphax-wiz-type-info">
                  <div class="alphax-wiz-type-label">${t.label}</div>
                  <div class="alphax-wiz-type-tagline">${t.tagline}</div>
                </div>
              </label>
            `).join('')}
          </div>
        </div>`;
    }
    else if (state.step === 4){
      html = `
        <h2>This cashier station</h2>
        <div class="alphax-wiz-field">
          <label>Terminal name <span class="alphax-req">*</span></label>
          <input class="alphax-input" data-field="terminal_name" value="${esc(state.terminal.name)}" placeholder="e.g. Terminal 1, or A07" autofocus/>
          <small>A short label for this physical PC.</small>
        </div>
        <div class="alphax-wiz-field">
          <label>PC Hostname (optional)</label>
          <input class="alphax-input" data-field="pc_hostname" value="${esc(state.terminal.pc_hostname)}" placeholder="e.g. WIN-A4F2"/>
          <small>Helpful for IT troubleshooting later. Leave blank if you don't know it.</small>
        </div>
        <div class="alphax-wiz-info-card">
          <b>What happens next:</b><br>
          We'll bind this PC to the terminal you just named. From now on, opening
          the cashier on this PC will load straight into Terminal "${esc(state.terminal.name)}".
        </div>`;
    }
    else if (state.step === 5){
      html = `
        <h2>Create your admin account</h2>
        <div class="alphax-wiz-field">
          <label>Your full name <span class="alphax-req">*</span></label>
          <input class="alphax-input" data-field="admin_name" value="${esc(state.admin.full_name)}" placeholder="e.g. Noor Al-Saudi" autofocus/>
        </div>
        <div class="alphax-wiz-field">
          <label>Your email <span class="alphax-req">*</span></label>
          <input class="alphax-input" type="email" data-field="admin_email" value="${esc(state.admin.email)}" placeholder="you@example.com"/>
          <small>You'll log in with this email. We'll email you a password reset link after setup.</small>
        </div>
        <div class="alphax-wiz-field">
          <label>Manager PIN <span class="alphax-req">*</span></label>
          <input class="alphax-input" type="password" maxlength="6" pattern="[0-9]*" inputmode="numeric"
                 data-field="admin_pin" value="${esc(state.admin.pin)}" placeholder="4-6 digits"/>
          <small>Used at the cashier counter to authorize discounts, returns, station setup. <b>Memorize it</b> — we don't store the plain PIN, only its bcrypt hash.</small>
        </div>
        <div class="alphax-wiz-info-card alphax-wiz-info-final">
          <b>Ready?</b> Click "Finish setup" to create everything. Takes about
          5-10 seconds. After that, you'll land on the cashier register.
        </div>`;
    }
    $form.html(html);

    // Update Next button label on last step
    const $next = $(wrapper).find('[data-action="next"]');
    if (state.step === 5) $next.html('<span class="alphax-btn-icon">✓</span> Finish setup');
    else $next.html('Next →');

    const $prev = $(wrapper).find('[data-action="prev"]');
    if (state.step === 1) $prev.css('visibility', 'hidden');
    else $prev.css('visibility', 'visible');
  }

  function esc(s){
    return $('<div>').text(s || '').html();
  }

  // Capture form values into state when moving forward
  function capture(){
    const $f = $(wrapper).find('[data-area="form"]');
    if (state.step === 1){
      const $sel = $f.find('[data-field="company_select"]');
      if ($sel.length){
        const v = $sel.val();
        if (v === '__new__'){ state.company.mode = 'new'; state.company.existing = ''; }
        else { state.company.mode = 'existing'; state.company.existing = v; }
      } else {
        state.company.mode = 'new';
      }
      if (state.company.mode === 'new'){
        state.company.name     = ($f.find('[data-field="company_name"]').val() || '').trim();
        state.company.vat      = ($f.find('[data-field="company_vat"]').val() || '').trim();
        state.company.currency = $f.find('[data-field="company_currency"]').val() || state.company.currency;
        state.company.country  = $f.find('[data-field="company_country"]').val() || state.company.country;
      } else {
        // Reuse the selected existing company; its name IS the company name.
        state.company.name = state.company.existing;
      }
    } else if (state.step === 2){
      const $sel = $f.find('[data-field="branch_select"]');
      if ($sel.length){
        const v = $sel.val();
        if (v === '__new__'){ state.branch.mode = 'new'; state.branch.existing = ''; }
        else { state.branch.mode = 'existing'; state.branch.existing = v; }
      } else {
        state.branch.mode = 'new';
      }
      if (state.branch.mode === 'new'){
        state.branch.name    = ($f.find('[data-field="branch_name"]').val() || '').trim();
        state.branch.address = ($f.find('[data-field="branch_address"]').val() || '').trim();
      } else {
        state.branch.name = state.branch.existing;
      }
    } else if (state.step === 3){
      state.outlet.name   = ($f.find('[data-field="outlet_name"]').val() || '').trim();
      state.outlet.domain = $f.find('input[name="domain"]:checked').val() || 'Generic';
    } else if (state.step === 4){
      state.terminal.name        = ($f.find('[data-field="terminal_name"]').val() || '').trim();
      state.terminal.pc_hostname = ($f.find('[data-field="pc_hostname"]').val() || '').trim();
    } else if (state.step === 5){
      state.admin.full_name = ($f.find('[data-field="admin_name"]').val() || '').trim();
      state.admin.email     = ($f.find('[data-field="admin_email"]').val() || '').trim();
      state.admin.pin       = ($f.find('[data-field="admin_pin"]').val() || '').trim();
    }
  }

  function validate_current(){
    capture();
    const errs = [];
    if (state.step === 1){
      if (!state.company.name) errs.push('Company name is required.');
    } else if (state.step === 2){
      if (!state.branch.name) errs.push('Branch name is required.');
    } else if (state.step === 3){
      if (!state.outlet.name) errs.push('Outlet name is required.');
    } else if (state.step === 4){
      if (!state.terminal.name) errs.push('Terminal name is required.');
    } else if (state.step === 5){
      if (!state.admin.full_name) errs.push('Your name is required.');
      if (!state.admin.email || !state.admin.email.includes('@')) errs.push('A valid email is required.');
      if (!/^\d{4,6}$/.test(state.admin.pin)) errs.push('Manager PIN must be 4-6 digits.');
    }
    return errs;
  }

  $(wrapper).on('click', '[data-action="next"]', async function(){
    const errs = validate_current();
    if (errs.length){
      frappe.msgprint({
        title: 'Please fix:',
        message: errs.map(e => '• ' + e).join('<br>'),
        indicator: 'orange',
      });
      return;
    }
    if (state.step < 5){
      state.step++;
      render_step();
      // Try to capture PC hostname from navigator if user didn't fill it
      if (state.step === 4 && !state.terminal.pc_hostname){
        try {
          const probe = navigator.userAgent.match(/\(([^)]+)\)/);
          if (probe) state.terminal.pc_hostname = probe[1].split(';')[0].trim();
        } catch(e){}
        render_step();
      }
      return;
    }
    // Step 5 → finish setup
    await finish_setup();
  });

  $(wrapper).on('click', '[data-action="prev"]', function(){
    if (state.step > 1){
      capture();
      state.step--;
      render_step();
    }
  });

  // Radio click highlights the selected card
  $(wrapper).on('change', 'input[name="domain"]', function(){
    state.outlet.domain = this.value;
    $(wrapper).find('.alphax-wiz-type').removeClass('selected');
    $(this).closest('.alphax-wiz-type').addClass('selected');
  });

  // Switching between an existing record and "create new" re-renders the
  // step so the create-form shows/hides appropriately.
  $(wrapper).on('change', '[data-field="company_select"], [data-field="branch_select"]', function(){
    capture();
    render_step();
  });

  async function finish_setup(){
    const $next = $(wrapper).find('[data-action="next"]');
    $next.attr('disabled', true).html('Setting up...');

    try {
      const r = await frappe.call({
        method: 'alphax_pos_suite.alphax_pos_suite.boot.api.run_setup_wizard',
        args: { payload: state }
      });
      const m = r.message || {};
      if (m.ok){
        // Save the bound terminal in localStorage so the cashier loads
        // straight into it.
        try {
          localStorage.setItem('alphax_pos_classic_terminal_v1', m.terminal);
        } catch(e){}
        frappe.show_alert({
          message: '✓ Setup complete! Loading cashier...',
          indicator: 'green'
        }, 4);
        setTimeout(() => {
          frappe.set_route('alphax-pos-classic');
        }, 1200);
      } else {
        frappe.msgprint({
          title: 'Setup did not complete',
          message: m.message || 'Unknown error. Check the Error Log.',
          indicator: 'red'
        });
        $next.removeAttr('disabled').html('Try again');
      }
    } catch(e){
      const msg = (e && e.message) ? e.message : 'Setup failed. Check the Error Log.';
      frappe.msgprint({ title: 'Setup error', message: msg, indicator: 'red' });
      $next.removeAttr('disabled').html('Try again');
    }
  }

  // Cleanup on navigate away
  frappe.router.on('change', function cleanup(){
    if (frappe.get_route_str().indexOf('alphax-pos-setup-wizard') === -1){
      $('body').removeClass('alphax-pos-wizard-page');
      frappe.router.off('change', cleanup);
    }
  });

  // Load existing companies/branches so the user can select rather than
  // create duplicates, then (re)render. A clean/new site simply gets the
  // create-new form.
  frappe.call({ method: 'alphax_pos_suite.alphax_pos_suite.boot.api.get_setup_wizard_context' })
    .then(r => {
      ctx = (r && r.message) ? r.message : ctx;
      if ((ctx.companies || []).length){
        state.company.mode = 'existing';
        state.company.existing = ctx.companies[0].name;
        if (ctx.companies[0].default_currency) state.company.currency = ctx.companies[0].default_currency;
        if (ctx.companies[0].country) state.company.country = ctx.companies[0].country;
      } else {
        state.company.mode = 'new';
      }
      if ((ctx.branches || []).length){
        state.branch.mode = 'existing';
        state.branch.existing = ctx.branches[0];
      } else {
        state.branch.mode = 'new';
      }
      render_step();
    })
    .catch(() => render_step());

  render_step();
};
