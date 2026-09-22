# AlphaX POS Suite v15.8.4 — Day close 1054 fix

Day close read `company` from AlphaX POS Terminal, which has no such
column (1054 Unknown column 'company' in 'SELECT'). Company now
resolves through the chain that always exists: the terminal's POS
Profile → its company, falling back to the site default company.
Shift close itself verified working in the field (net 230.00, drawer
balanced) — this unblocks the final step of the cash-control loop.
