const byId = (id) => document.getElementById(id);

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = String(text);
  return node;
}

// Call renderCase(yourJsonObject) when connecting another JSON source.
function renderCase(data) {
  byId('role').textContent = `Role: ${data.role || '—'} | Queue: ${data.queue || '—'}`;
  const summary = byId('summary');
  summary.replaceChildren();
  for (const [label, value] of [
    ['PA #', data.paNumber], ['Drug', data.drug],
    ['Line of Business', data.lineOfBusiness], ['Origin', data.origin]
  ]) {
    const field = element('div');
    field.append(element('span', 'summary-label', label), element('div', 'summary-value', value || '—'));
    summary.append(field);
  }
  byId('pac').textContent = data.pa?.pac || '—';
  byId('psg').textContent = data.pa?.psg || '—';
  byId('urgent').checked = data.pa?.urgent === true;
  byId('member-info').replaceChildren();
  const member = data.member && typeof data.member === 'object' ? data.member : {};
  for (const [label, value] of Object.entries(member)) {
    byId('member-info').append(element('dt', '', label), element('dd', '', value ?? '—'));
  }
  if (!Object.keys(member).length) {
    byId('member-info').append(element('dd', '', 'No member information provided.'));
  }
  const steps = byId('steps');
  steps.replaceChildren();
  for (const [index, step] of (Array.isArray(data.steps) ? data.steps : []).entries()) {
    const state = ['complete', 'review', 'pending'].includes(step.state) ? step.state : 'pending';
    const card = element('details', `step ${state === 'review' ? 'review-state' : state}`);
    const heading = element('summary');
    const chevron = element('span', 'chevron', '▾');
    chevron.setAttribute('aria-hidden', 'true');
    heading.append(element('span', 'number', index + 1), element('span', 'step-title', step.title || 'Review step'),
      element('span', 'badge', `${state === 'complete' ? '✓ ' : ''}${step.status || 'Not Started'}`), chevron);
    const content = element('div', 'step-content');
    renderStepContent(content, step, data);
    card.append(heading, content);
    steps.append(card);
  }
  byId('workspace').hidden = false;
}

async function loadCase() {
  try {
    const response = await fetch('/api/case', { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Unable to load case data.');
    renderCase(data);
  } catch (error) {
    byId('error').textContent = error.message;
    byId('error').hidden = false;
  }
}

function button(text, action, secondary = false) {
  const node = element('button', secondary ? 'text-button' : 'primary-button', text);
  node.type = 'button';
  node.addEventListener('click', action);
  return node;
}

function field(label, value, type = 'text', options) {
  const wrapper = element('label', 'form-field');
  wrapper.append(element('span', '', label));
  const input = element(options ? 'select' : 'input');
  if (options) {
    for (const option of options) {
      const item = typeof option === 'string' ? { value: option, label: option } : option;
      const node = element('option', '', item.label);
      node.value = item.value;
      input.append(node);
    }
  } else {
    input.type = type;
    if (type === 'number') { input.min = '1'; input.step = '1'; input.required = true; }
  }
  input.value = value ?? '';
  wrapper.append(input);
  return { wrapper, input };
}

function disclosure(title, content, open = true) {
  const node = element('details', 'inner-disclosure');
  node.open = open;
  node.append(element('summary', '', title), content);
  return node;
}

function renderStepContent(target, step, data) {
  const config = data[step.type] || {};
  if (step.type === 'drugVerification') {
    target.append(element('p', 'verification-message', `✓ ${config.message || ''}`));
    const chips = element('div', 'chips');
    const submittedChip = element('span', 'chip', `Drug name: ${config.submittedName || '—'}`);
    const requestedChip = element('span', 'chip', `Requested drug: ${data.drug || '—'}`);
    chips.append(submittedChip, requestedChip, element('span', 'chip', `NDC ${config.ndc || '—'}`), element('span', 'chip', `GPI/GCN ${config.gpi || '—'}`));
    const form = element('form', 'form-panel');
    const submitted = field('Drug name (as submitted)', config.submittedName);
    const requested = field('Requested drug', data.drug, 'text', [...new Set([data.drug, ...(config.requestedDrugOptions || [])].filter(Boolean))]);
    const feedback = element('p', 'feedback');
    feedback.setAttribute('role', 'status');
    const actions = element('div', 'actions');
    const save = element('button', 'primary-button', 'Save');
    save.type = 'submit';
    actions.append(save, button('Cancel', () => { form.reset(); feedback.textContent = 'Edits cancelled.'; }, true));
    form.append(element('h3', '', 'Edit Drug'), submitted.wrapper, requested.wrapper, actions, feedback);
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      config.submittedName = submitted.input.value;
      data.drug = requested.input.value;
      submitted.input.defaultValue = submitted.input.value;
      for (const option of requested.input.options) option.defaultSelected = option.selected;
      submittedChip.textContent = `Drug name: ${config.submittedName}`;
      requestedChip.textContent = `Requested drug: ${data.drug}`;
      byId('summary').children[1].querySelector('.summary-value').textContent = data.drug;
      feedback.textContent = 'Saved for this preview. Refresh reloads the JSON file.';
    });
    target.append(chips, form);
  } else if (step.type === 'paHistory') {
    target.append(element('p', '', `✓ ${config.summary || ''}`));
    const table = element('table', 'history-table');
    const head = element('thead');
    const row = element('tr');
    for (const text of ['PA Number', 'Drug', 'Date', 'Status']) { const th = element('th', '', text); th.scope = 'col'; row.append(th); }
    head.append(row);
    const body = element('tbody');
    for (const record of config.records || []) {
      const tr = element('tr', record.current ? 'current-row' : '');
      const number = element('td', '', record.number);
      if (record.current) number.append(element('span', 'current-tag', 'current'));
      const status = element('td', record.state === 'denied' ? 'denied-text' : 'review-text', `${record.state === 'denied' ? '✗' : '•'} ${record.status}`);
      tr.append(number, element('td', '', record.drug), element('td', '', record.date), status);
      body.append(tr);
    }
    table.append(head, body);
    const scroll = element('div', 'table-scroll'); scroll.append(table);
    target.append(disclosure('PA History', scroll));
  } else if (step.type === 'mockClaim') {
    const result = element('div', 'result-box');
    result.append(element('strong', '', `✓ ${config.resultTitle || ''}`), element('p', '', config.resultDetail || ''), element('p', '', config.message || ''));
    const form = element('form', 'form-panel');
    const grid = element('div', 'form-grid');
    const inputs = {};
    for (const [key, label, type] of [
      ['drugName', 'Drug name', 'text'], ['ndc', 'NDC', 'text'], ['quantity', 'Quantity', 'number'],
      ['daysSupply', 'Days supply', 'number'], ['pharmacyId', 'Pharmacy ID', 'text'],
      ['fillDate', 'Fill date', 'date'], ['physicianId', 'Physician ID', 'text'], ['productSelectionCode', 'Product selection code', 'text']
    ]) {
      const control = field(label, config[key], type, key === 'productSelectionCode' ? config.productSelectionOptions : undefined);
      inputs[key] = control.input;
      grid.append(control.wrapper);
    }
    const run = element('button', 'primary-button', 'Run Mock Claim'); run.type = 'submit';
    const feedback = element('p', 'feedback'); feedback.setAttribute('role', 'status');
    form.append(element('h3', '', 'Manual Mock Claim'), grid, run, feedback);
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      feedback.textContent = 'Sample result displayed from JSON. No claim was sent.';
      result.replaceChildren(element('strong', '', `✓ ${config.resultTitle || ''}`),
        element('p', '', `${inputs.drugName.value} · ${inputs.quantity.value} tablets · ${inputs.daysSupply.value}-day supply · Filled ${inputs.fillDate.value}`),
        element('p', '', config.message || ''));
    });
    target.append(result, disclosure('Manual Mock Claim', form));
  } else if (step.type === 'criteriaReview') {
    target.append(element('p', 'criteria-title', config.title || ''), element('div', 'notice warning', `ϟ ${config.fallout || ''}`), element('div', 'notice', `⚠ ${config.notice || ''}`));
    const list = element('div', 'questions');
    const controls = [];
    for (const question of config.questions || []) {
      const detail = element('details', 'question');
      const heading = element('summary');
      heading.append(element('span', 'question-id', question.id), element('strong', 'question-label', question.label), element('span', 'answer-tag', question.answer || '—'),
        element('span', `question-status ${question.state || 'pending'}`, question.status), element('span', 'chevron', '▾'));
      const body = element('div', 'question-detail');
      body.append(element('p', '', question.detail || 'Answer and verification status supplied by the JSON file.'));
      const answer = field('Answer', question.answer, 'text', ['', 'Yes', 'No']);
      answer.input.disabled = true;
      controls.push({ input: answer.input, question, tag: heading.querySelector('.answer-tag') });
      body.append(answer.wrapper);
      detail.append(heading, body); list.append(detail);
    }
    const feedback = element('p', 'feedback'); feedback.setAttribute('role', 'status');
    let editing = false;
    const edit = button('Edit', () => {
      editing = !editing;
      controls.forEach(({ input, question, tag }) => {
        input.disabled = !editing;
        if (!editing) { question.answer = input.value; tag.textContent = input.value || '—'; }
      });
      edit.textContent = editing ? 'Save' : 'Edit';
      feedback.textContent = editing ? 'Expand a question to edit its sample answer.' : 'Answers updated for this preview. Score and verification statuses remain supplied by JSON.';
    });
    const score = element('div', 'score-area');
    score.append(element('span', 'score', `✓ ${config.result || '—'}`), element('p', '', 'Score from JSON · verification pending'));
    target.append(list, edit, feedback, score);
  } else if (step.type === 'notes') {
    const wrapper = element('div', 'notes-editor');
    const textarea = element('textarea');
    textarea.setAttribute('aria-label', 'Case notes');
    textarea.maxLength = Number.isInteger(config.maxLength) && config.maxLength > 0 ? config.maxLength : 3000;
    textarea.placeholder = config.placeholder || 'Enter or generate notes...';
    textarea.value = String(config.text || '').slice(0, textarea.maxLength);
    const counter = element('p', 'character-count'); counter.setAttribute('aria-live', 'polite');
    const update = () => { counter.textContent = `Characters remaining: ${textarea.maxLength - textarea.value.length}`; };
    textarea.addEventListener('input', update);
    wrapper.append(textarea, button('Generate Notes', () => { textarea.value = String(config.generatedText || '').slice(0, textarea.maxLength); update(); }, true));
    update(); target.append(wrapper, counter, element('p', 'local-hint', 'Preview only. Notes are not saved after refresh.'));
  } else if (step.type === 'caseDecision') {
    target.append(element('p', '', config.message || 'Waiting on verification.'));
  } else {
    target.append(element('p', '', step.content || 'No details provided.'));
  }
}

loadCase();
