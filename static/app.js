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
    content.append(element('p', '', step.content || 'Details and dropdown options will be added here.'));
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

loadCase();
