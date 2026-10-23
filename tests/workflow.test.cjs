const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.join(__dirname, '..');

function setup() {
  const data = JSON.parse(fs.readFileSync(path.join(root, 'data/case.json'), 'utf8'));
  const fields = {};
  const context = vm.createContext({
    window: { PA_DATA: data },
    document: { getElementById: id => fields[id] || null },
    console, Date,
  });
  vm.runInContext(fs.readFileSync(path.join(root, 'static/app.js'), 'utf8'), context);
  return { context, fields, run: code => vm.runInContext(code, context), data };
}
const plain = value => JSON.parse(JSON.stringify(value));

test('initial prescriber path scores A but Q4 prevents a decision', () => {
  const { run } = setup();
  assert.deepEqual(plain(run('path(sa[0][0])')), { steps: [1, 2, 3, 4, 5, 6], terminal: 'A' });
  assert.deepEqual(plain(run('pendingVerify()')), [4]);
  run('decYes(); decConfirmApprove()');
  assert.equal(run('getWf().decision'), null);
});

test('weight verification unlocks approval and exports the matching snapshot', () => {
  const { run } = setup();
  run("getWf().calc={w0:'174',w1:'128'}; confirmCalc(4); decYes(); decConfirmApprove()");
  const output = plain(run('reviewOutput()'));
  assert.equal(output.decision.action, 'approve');
  assert.equal(output.decision.score, 'A');
  assert.deepEqual(output.pendingVerification, []);
  assert.ok(Math.abs(output.weightCalculation.percentLoss - 26.43678) < 0.001);
});

test('failed weight threshold follows Denial and never records Approval', () => {
  const { run } = setup();
  run("getWf().calc={w0:'200',w1:'199'}; confirmCalc(4); decYes()");
  assert.match(run('renderStep6(getCase())'), /Confirm Denial/);
  run('decConfirmApprove()');
  assert.equal(run('getWf().decision.action'), 'deny');
  assert.equal(run('score(sa[0][0])'), 'D');
  assert.equal(run('sa[0][0][5]'), undefined);
});

test('path changes prune stale answers, restore initial answers, and revoke decisions', () => {
  const { run } = setup();
  run("getWf().calc={w0:'174',w1:'128'}; confirmCalc(4); decYes(); decConfirmApprove(); setAnsV3(4,'F')");
  assert.equal(run('getWf().decision'), null);
  assert.equal(run('sa[0][0][6]'), undefined);
  run("setAnsV3(4,'T')");
  assert.equal(run('sa[0][0][6]'), 'F');
  assert.equal(run('score(sa[0][0])'), 'A');
});

test('changing weight inputs revokes verification and any completed decision', () => {
  const { run, fields } = setup();
  run("getWf().calc={w0:'174',w1:'128'}; confirmCalc(4); decYes(); decConfirmApprove()");
  fields['cw0-4'] = { value: '174' };
  fields['cw1-4'] = { value: '170' };
  run('updCalc(4)');
  assert.equal(run('getWf().decision'), null);
  assert.equal(run('canDecide()'), false);
  run('decConfirmApprove()');
  assert.equal(run('getWf().decision'), null);
});

test('calculator rejects zero, negatives, and non-finite values', () => {
  const { run } = setup();
  for (const value of ['0', '-1', 'Infinity', 'abc', '']) {
    run(`getWf().calc={w0:${JSON.stringify(value)},w1:'128'}`);
    assert.equal(run('calcPct()'), null);
  }
});

test('notes reflect actual verification and edited values', () => {
  const { run } = setup();
  run('genNoteV3()');
  assert.match(run('getWf().s5Text'), /Pending verification/);
  assert.match(run('getWf().s5Text'), /Manually verified: None/);
  run("getWf().calc={w0:'200',w1:'199'}; confirmCalc(4); genNoteV3()");
  assert.match(run('getWf().s5Text'), /0\.5%/);
  assert.match(run('getWf().s5Text'), /Denial/);
});

test('mock form inputs survive rerenders and export the last run independently', () => {
  const { run, fields } = setup();
  for (const [id, value] of Object.entries({ 'mc-qty': '60', 'mc-days': '60', 'mc-pharm': '2221113', 'mc-fill': '07/23/2026', 'mc-phys': '123', 'mc-psc': '2' })) fields[id] = { value };
  run('runMockClaim()');
  assert.equal(run('reviewOutput().mockClaim.lastRunInput.qty'), '60');
  fields['mc-qty'].value = '90';
  run('captureMockInput()');
  assert.equal(run('reviewOutput().mockClaim.input.qty'), '90');
  assert.equal(run('reviewOutput().mockClaim.lastRunInput.qty'), '60');
  assert.match(run('renderStep2(getCase())'), /value="90"/);
  assert.match(run('renderStep2(getCase())'), /value="2" selected/);
});

test('text data and textarea delimiters are escaped during HTML rendering', () => {
  const { run, data } = setup();
  data.cases[0].meta.submittedDrug = '<img src=x onerror=alert(1)>';
  assert.doesNotMatch(run('renderStep1(getCase())'), /<img src=x/);
  run("getWf().s5Text='</textarea><script>alert(1)</script>'");
  assert.match(run('renderStep5(getCase())'), /&lt;\/textarea&gt;&lt;script&gt;/);
});

test('cyclic or incomplete question paths cannot produce a decision', () => {
  const { run, data } = setup();
  data.skipLogic[1].T = 1;
  assert.equal(run('score(sa[0][0])'), null);
  assert.equal(run('canDecide()'), false);
});
