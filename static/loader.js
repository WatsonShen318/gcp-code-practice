async function loadReview() {
  try {
    const response = await fetch('/api/case', { cache: 'no-store' });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Unable to load case data.');
    if (data.schemaVersion !== 2 || !Array.isArray(data.cases) || !data.cases.length ||
        !data.skipLogic || !data.questionMetadata || !Array.isArray(data.drugOptions)) {
      throw new Error('Invalid review JSON. Use the schemaVersion 2 example in data/case.json.');
    }
    const ids = new Set();
    if (!data.skipLogic[1]) throw new Error('The question path must start at Q1.');
    for (const [key, branch] of Object.entries(data.skipLogic)) {
      if (!/^[1-9]\d*$/.test(key) || !data.questionMetadata[key] || !branch ||
          !['T', 'F'].every(answer => ['A', 'D'].includes(branch[answer]) ||
            (Number.isInteger(branch[answer]) && branch[answer] > 0 && data.skipLogic[branch[answer]]))) {
        throw new Error('Invalid question number or skip-logic destination.');
      }
    }
    for (const reviewCase of data.cases) {
      if (!reviewCase.id || ids.has(reviewCase.id) || !reviewCase.meta || !reviewCase.member || !reviewCase.claim ||
          !Array.isArray(reviewCase.legs) || !reviewCase.legs.length) {
        throw new Error('Each case needs a unique id, meta, member, claim, and at least one review leg.');
      }
      ids.add(reviewCase.id);
    }
    data.mockClaimDefaults ||= {};
    data.mockClaimResults ||= {};
    data.caseNotes ||= {};
    data.toolData ||= {};
    window.PA_DATA = data;
    const script = document.createElement('script');
    script.src = '/static/app.js';
    script.onload = () => {
      try {
        window.startApp();
        document.getElementById('export-json').disabled = false;
      } catch (error) { showLoadError(error); }
    };
    script.onerror = () => showLoadError(new Error('Unable to load the review interface.'));
    document.body.append(script);
  } catch (error) { showLoadError(error); }
}

function showLoadError(error) {
  const message = document.createElement('div');
  message.className = 'load-error';
  message.setAttribute('role', 'alert');
  message.textContent = `Could not load review: ${error.message}`;
  document.getElementById('wf-steps').replaceChildren(message);
}

loadReview();
