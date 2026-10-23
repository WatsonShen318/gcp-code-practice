const {skipLogic:SK,questionMetadata:QM,cases:CASES,drugOptions:DRUG_LIST,mockClaimDefaults:MOCK_CLAIM_DEFS,mockClaimResults:MC_RESULTS,caseNotes:CASE_NOTES,toolData:TOOL_DATA} = window.PA_DATA;

// ── STATE ─────────────────────────────────────────────────────────────────────
let curCase=0, curLeg=0;
let sa=CASES.map(c=>c.legs.map(l=>Object.assign({},l.initAns||{})));

function mkWfSt(){
  return{
    s1Open:false, s1Edit:false,
    s2Card:false, s2Open:false, s2Ran:false, s2Tab:'msg',
    s3Open:false, s3Exp:false,
    s4Open:false, s4Edit:false, calc:{w0:'',w1:''}, qOpen:{}, verified:{},
    s5Open:false, s5Gen:false, s5Text:'',
    s6Open:false, s6State:'idle', s6AltOpt:null, decision:null, mcInput:null, mcRunInput:null,
  };
}
let wfSt=CASES.map(c=>c.legs.map(()=>mkWfSt()));

// ── PATH / SKIP ───────────────────────────────────────────────────────────────
function path(ans){
  const steps=[], seen=new Set(); let q=1;
  while(q!=='A'&&q!=='D'){
    if(seen.has(q)||!SK[q]||!QM[q])return{steps,terminal:null};
    seen.add(q);
    steps.push(q);
    const a=ans[q];
    if(a!=='T'&&a!=='F')return{steps,terminal:null};
    const nxt=SK[q]?.[a==='T'?'T':'F'];
    if(!nxt)return{steps,terminal:null};
    q=nxt;
  }
  return{steps,terminal:q};
}
function prune(ans){
  const{steps}=path(ans), keep=new Set(steps), out={};
  Object.keys(ans).forEach(k=>{if(keep.has(Number(k)))out[k]=ans[k];});
  return out;
}
function score(ans){return path(ans).terminal;}

// ── HELPERS ───────────────────────────────────────────────────────────────────
function el(id){return document.getElementById(id);}
function escapeHtml(value){return String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));}
function getCase(){return CASES[curCase];}
function getLeg(){return CASES[curCase].legs[curLeg];}
function getWf(){return wfSt[curCase][curLeg];}
function invalidateDecision(){
  const wf=getWf();
  wf.s6State='idle'; wf.s6AltOpt=null; wf.decision=null;
  if(wf.s5Gen){
    wf.s5Text='';wf.s5Gen=false;
    const notes=el('notes-ta');if(notes)notes.value='';
    const counter=el('ncount');if(counter)counter.textContent='Characters remaining: 3000';
    const badge=el('step-5')?.querySelector('.wf-status');
    if(badge){badge.textContent='○ Not Started';badge.className='wf-status st-pending';}
  }
}

// ── LAYOUT ────────────────────────────────────────────────────────────────────
function updateTop(){
  const hasLegs=getCase().legs.length>1;
  const style=getComputedStyle(document.documentElement);
  document.documentElement.style.setProperty('--layout-top',(parseFloat(style.getPropertyValue('--bar'))+parseFloat(style.getPropertyValue('--strip'))+(hasLegs?36:0))+'px');
}
function renderBarRole(){
  const leg=getLeg();
  const b=el('bar-role');
  if(b)b.textContent=`Role: ${leg.role||'Pharmacist'}  |  Queue: ${leg.queue||'Work Queue'}`;
}
function syncDemoSel(){const s=el('demo-sel');if(s)s.value=String(curCase);}
function renderStrip(){
  const c=getCase();
  el('strip').innerHTML=`
    <div class="sf"><span class="sf-lbl">PA #</span><span class="sf-val b">${escapeHtml(c.id)}</span></div>
    <div class="strip-div"></div>
    <div class="sf"><span class="sf-lbl">Drug</span><span class="sf-val b">${escapeHtml(c.meta.requestedDrug||c.meta.drug)}</span></div>
    <div class="strip-div"></div>
    <div class="sf"><span class="sf-lbl">Line of Business</span><span class="sf-val">${escapeHtml(c.meta.lob)}</span></div>
    <div class="strip-div"></div>
    <div class="sf"><span class="sf-lbl">Origin</span><span class="sf-val">${escapeHtml(c.meta.origin)}</span></div>`;
}
function renderLegBar(){
  const c=getCase(), bar=el('leg-bar');
  if(c.legs.length<=1){bar.style.display='none';return;}
  bar.style.display='flex';
  bar.innerHTML=c.legs.map((l,i)=>`
    <button class="ltab${i===curLeg?' act':''}" onclick="selectLeg(${i})">
      ${l.isAgent?'<span class="ai-dot">AI</span>':''}Leg ${i+1}: ${escapeHtml(l.role)}
    </button>`).join('');
}

// ── LEFT PANEL ────────────────────────────────────────────────────────────────
function renderMember(){
  const m=getCase().member;
  el('mbr-body').innerHTML=`
    <div class="mgrid">
      <div class="mr"><span class="ml">Member ID</span><span class="mv">${escapeHtml(m.id)}</span></div>
      <div class="mr"><span class="ml">Name</span><span class="mv">${escapeHtml(m.name)}</span></div>
      <div class="mr"><span class="ml">DOB</span><span class="mv">${escapeHtml(m.dob)}</span></div>
      <div class="mr"><span class="ml">Sex</span><span class="mv">${escapeHtml(m.sex)}</span></div>
    </div>`;
}
function renderPAInfo(){
  const c=getCase();
  const urgKey=`urgent-${c.id}`;
  let isUrgent=!!c.meta.urgent;try{const sv=localStorage.getItem(urgKey);if(sv!==null)isUrgent=(sv==='true');}catch(e){}
  c.meta.urgent=isUrgent;
  el('pai-body').innerHTML=`
    <div class="pai-grid">
      <div class="pairow"><span class="pail">PAC</span><span class="paiv">${escapeHtml(c.meta.cls)}</span></div>
      <div class="pairow"><span class="pail">PAG</span><span class="paiv">${escapeHtml(c.member.pag)}</span></div>
      <label class="urgent-row${isUrgent?' is-urgent':''}" id="urgent-row">
        <input type="checkbox" class="urgent-cb" id="urgent-cb" ${isUrgent?'checked':''} onchange="toggleUrgent(this)">
        <span class="urgent-lbl">${isUrgent?'Urgent ⚑':'Urgent'}</span>
      </label>
    </div>`;
}
function toggleUrgent(cb){
  const c=getCase();
  c.meta.urgent=cb.checked;
  try{localStorage.setItem(`urgent-${c.id}`,String(cb.checked));}catch(e){}
  const row=el('urgent-row');
  if(row){
    row.classList.toggle('is-urgent',cb.checked);
    row.querySelector('.urgent-lbl').textContent=cb.checked?'Urgent ⚑':'Urgent';
  }
}
function toggleSec(id){
  const b=el(id+'-body'), ic=el(id+'-icon'); if(!b)return;
  const open=b.style.display!=='none';
  b.style.display=open?'none':'block';
  if(ic)ic.textContent=open?'▼':'▲';
}
function renderMemberCenter(){
  el('mc-body').innerHTML=`
    <div class="mc-btns">
      <button class="mc-btn" onclick="openTool('member-search')"><span class="mc-ico">🔍</span><span class="mc-lbl">Member Search</span><span class="mc-arr">↗</span></button>
      <button class="mc-btn" onclick="openTool('pa-history')"><span class="mc-ico">📋</span><span class="mc-lbl">PA History</span><span class="mc-arr">↗</span></button>
      <button class="mc-btn" onclick="openTool('claim-history')"><span class="mc-ico">💊</span><span class="mc-lbl">Claim History</span><span class="mc-arr">↗</span></button>
    </div>`;
}

// ── TOOL DATA ─────────────────────────────────────────────────────────────────
function openTool(name){
  const c=getCase(), m=c.member, td=TOOL_DATA[c.id]||{paHistory:[],claimHistory:[]};
  const modal=el('tool-modal'), body=el('tool-body');
  if(!modal||!body)return;
  if(name==='member-search'){
    el('tool-ttl').textContent='Member Search'; el('tool-sub').textContent='CVS Caremark Member Portal';
    body.innerHTML=`<div class="tool-search-bar"><input class="tool-input" id="member-query" aria-label="Member ID or name" type="text" value="${escapeHtml(m.id)}"><button class="tool-srch-btn" onclick="searchMember()">Search</button></div><div id="member-match" role="status"></div>
      <div class="tool-result-card">
        <div class="trcard-hdr"><span class="trcard-ttl">${escapeHtml(m.name)}</span><span class="trcard-badge tc-active">● Active</span></div>
        <div class="trow"><span class="trl">Member ID</span><span class="trv">${escapeHtml(m.id)}</span></div>
        <div class="trow"><span class="trl">Date of Birth</span><span class="trv">${escapeHtml(m.dob)}</span></div>
        <div class="trow"><span class="trl">Sex</span><span class="trv">${escapeHtml(m.sex)}</span></div>
        <div class="trow"><span class="trl">Plan / PAG</span><span class="trv">${escapeHtml(m.pag)}</span></div>
        <div class="trow"><span class="trl">Eligibility</span><span class="trv">01/01/2026 – 12/31/2026</span></div>
        <div class="trow"><span class="trl">Line of Business</span><span class="trv">${escapeHtml(c.meta.lob)}</span></div>
        <div class="trow"><span class="trl">Client</span><span class="trv">${escapeHtml(c.meta.client)}</span></div>
      </div>`;
  }else if(name==='pa-history'){
    el('tool-ttl').textContent='PA History'; el('tool-sub').textContent=`${m.name}  ·  ${m.id}`;
    body.innerHTML=buildPAHistoryTbl(td.paHistory,c.id);
  }else if(name==='claim-history'){
    el('tool-ttl').textContent='Claim History'; el('tool-sub').textContent=`${m.name}  ·  ${m.id}`;
    body.innerHTML=buildClaimHistoryTbl(td.claimHistory);
  }
  modal.style.display='flex'; document.body.style.overflow='hidden';
}
function buildPAHistoryTbl(history=[],currentId){
  const rows=history.map(h=>{
    const cur=h.pa===currentId;
    const badge=h.outcome==='A'?'<span class="tb-a">✓ Approved</span>':h.outcome==='D'?'<span class="tb-d">✗ Denied</span>':'<span class="tb-r">● In Review</span>';
    return`<tr class="${cur?'tr-cur':''}"><td>${escapeHtml(h.pa)}${cur?' <span class="tr-cur-chip">current</span>':''}</td><td>${escapeHtml(h.drug)}</td><td>${escapeHtml(h.date)}</td><td>${badge}</td></tr>`;
  }).join('');
  return`<table class="tool-table"><thead><tr><th>PA Number</th><th>Drug</th><th>Date</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function buildClaimHistoryTbl(history=[]){
  const rows=history.map(h=>{
    const badge=h.status==='Paid'?'<span class="tb-a">✓ Paid</span>':'<span class="tb-d">✗ Rejected</span>';
    return`<tr><td>${escapeHtml(h.dt)}</td><td>${escapeHtml(h.drug)}</td><td>${escapeHtml(h.qty)}</td><td>${escapeHtml(h.days)}d</td><td>${badge}</td></tr>`;
  }).join('');
  return`<table class="tool-table"><thead><tr><th>Date</th><th>Drug</th><th>Qty</th><th>Days</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function closeTool(){const m=el('tool-modal');if(m){m.style.display='none';document.body.style.overflow='';}}
function closeToolOverlay(e){if(e.target===el('tool-modal'))closeTool();}
function searchMember(){
  const query=el('member-query').value.trim().toLowerCase(), m=getCase().member;
  const found=!!query&&[m.id,m.name].some(value=>String(value).toLowerCase().includes(query));
  el('tool-body').querySelector('.tool-result-card').hidden=!found;
  el('member-match').textContent=found?'1 matching member in the loaded case.':'No matching member in the loaded case.';
}

// ── DOCUMENT MODAL ────────────────────────────────────────────────────────────
function openDoc(qno){
  const leg=getLeg(), content=leg.docs&&leg.docs[qno];
  if(!content)return;
  const q=QM[qno];
  el('doc-ttl').textContent=q?`Q${qno} — ${q.s}`:`Q${qno} Chart Note`;
  el('doc-body').textContent=content;
  const modal=el('doc-modal');
  if(modal){modal.style.display='flex';document.body.style.overflow='hidden';}
}
function closeDoc(){const m=el('doc-modal');if(m){m.style.display='none';document.body.style.overflow='';}}
function closeDocOverlay(e){if(e.target===el('doc-modal'))closeDoc();}

// ── CRITERIA HELPERS ──────────────────────────────────────────────────────────
function calcPct(){
  const c=getWf().calc, w0=Number(c.w0), w1=Number(c.w1);
  return (Number.isFinite(w0)&&Number.isFinite(w1)&&w0>0&&w1>0)?(1-w1/w0)*100:null;
}
function renderCalc(qno){
  const wf=getWf(), c=wf.calc, pct=calcPct();
  const answered=!!wf.verified[qno];
  const pctTxt=pct!==null?pct.toFixed(1)+'%':'—';
  const pctCls=pct!==null?(pct>=5?'cpass':'cfail'):'';
  const rec=answered?`<div class="calc-rec">Recorded: ${sa[curCase][curLeg][qno]==='T'?'Yes':'No'}</div>`:'';
  return`<div class="calc">
    <div class="calc-hint">Enter the two weights to check the 5% threshold.</div>
    <div class="calc-fields">
      <div class="cf"><span class="clbl">Baseline (lbs)</span>
        <input class="cinp" id="cw0-${qno}" type="number" step="0.1" value="${escapeHtml(c.w0)}" oninput="updCalc(${qno})">
      </div>
      <div class="cf"><span class="clbl">Current (lbs)</span>
        <input class="cinp" id="cw1-${qno}" type="number" step="0.1" value="${escapeHtml(c.w1)}" oninput="updCalc(${qno})">
      </div>
      <div class="cf"><span class="clbl">% Loss</span>
        <div class="cres"><span id="cpct-${qno}" class="${pctCls}">${pctTxt}</span><span class="csub">≥5% required</span></div>
      </div>
      <button class="calc-confirm" id="cconf-${qno}" onclick="confirmCalc(${qno})" ${pct===null?'disabled':''}>${answered?'Update answer':'Use result'}</button>
    </div>${rec}
  </div>`;
}
function updCalc(qno){
  const wf=getWf();
  delete wf.verified[qno]; invalidateDecision();
  wf.calc.w0=el(`cw0-${qno}`)?.value||''; wf.calc.w1=el(`cw1-${qno}`)?.value||'';
  const pct=calcPct(), s=el(`cpct-${qno}`), btn=el(`cconf-${qno}`);
  if(s){s.textContent=pct!==null?pct.toFixed(1)+'%':'—'; s.className=pct!==null?(pct>=5?'cpass':'cfail'):'';}
  if(btn)btn.disabled=(pct===null);
  // Revoke completion immediately without replacing the focused weight input.
  const decisionBody=el('step-6-body');
  if(decisionBody){decisionBody.textContent='Weight inputs changed. Use result to verify the current values before deciding.';}
  const decisionBadge=el('step-6')?.querySelector('.wf-status');
  if(decisionBadge){decisionBadge.textContent='○ Waiting on verification';decisionBadge.className='wf-status st-pending';}
  const criteriaBadge=el('step-4')?.querySelector('.wf-status');
  if(criteriaBadge){criteriaBadge.textContent='Needs verification';criteriaBadge.className='wf-status st-warning';}
  const criteriaCard=el('step-4');
  if(criteriaCard){criteriaCard.classList.remove('wf-done');criteriaCard.classList.add('wf-input');}
  const qBadge=el(`qb-${qno}`)?.previousElementSibling?.querySelector('.abadge');
  if(qBadge){qBadge.textContent='NEEDS VERIFICATION';qBadge.className='dbadge';}
  const recorded=el(`qb-${qno}`)?.querySelector('.calc-rec');if(recorded)recorded.remove();
}
// Questions on the current path that ask the reviewer to verify the prescriber's answer
// (QM[q].act) and have not been verified yet.
function pendingVerify(){
  const wf=getWf(), {steps}=path(sa[curCase][curLeg]);
  return steps.filter(q=>QM[q]&&QM[q].act&&!wf.verified[q]);
}
// After an answer changes, bring back the prescriber's answers for any question that is on the
// new path but was dropped when the path was shorter (for example Q5 and Q6 after a No on Q4).
function restoreInit(ans){
  const init=getLeg().initAns||{};
  for(let i=0;i<60;i++){
    const {steps}=path(ans); let changed=false;
    steps.forEach(q=>{if(ans[q]===undefined&&init[q]!==undefined){ans[q]=init[q];changed=true;}});
    if(!changed)break;
  }
  return ans;
}
function confirmCalc(qno){
  const pct=calcPct(); if(pct===null)return;
  invalidateDecision();
  const val=pct>=5?'T':'F';
  let ans=Object.assign({},sa[curCase][curLeg]);
  ans[qno]=val; ans=prune(ans); ans[qno]=val; ans=restoreInit(ans);
  sa[curCase][curLeg]=ans; getWf().verified[qno]=true;
  renderWorkflow();
}
function toggleQ(qno){
  // Open state lives in the workflow state, so it survives re-renders (e.g. after "Use result").
  // The DOM is toggled directly rather than re-rendering, which would drop focus from an input.
  const b=el(`qb-${qno}`), ch=el(`chev-${qno}`); if(!b)return;
  const open=!getWf().qOpen[qno];
  getWf().qOpen[qno]=open;
  b.style.display=open?'block':'none';
  b.previousElementSibling?.setAttribute('aria-expanded',String(open));
  if(ch)ch.textContent=open?'▲':'▼';
}

function renderQCard(qno,ans,leg,isEdit){
  const q=QM[qno]; if(!q)return'';
  const a=ans[qno];
  const attnQs=leg.attnQs||[];
  const isAttn=attnQs.includes(qno);
  // badge: attnQs → "NEEDS ATTN." (amber), doc/act → "CHART REQ." (amber), auto → "Auto Verified" (green)
  let badge='';
  if(isAttn) badge='<span class="dbadge">NEEDS ATTN.</span>';
  else if(q.act) badge=getWf().verified[qno]?'<span class="abadge">Verified</span>':'<span class="dbadge">NEEDS VERIFICATION</span>';
  else if(q.att) badge='<span class="crbadge">Per submission</span>';
  else if((leg.notes&&leg.notes[qno])||(q.auto&&q.ev)) badge='<span class="abadge">Verified</span>';
  else badge='<span class="crbadge">Per submission</span>';

  const chip=(a!==undefined)?`<span class="achip ${a==='T'?'cy':'cn'}">${a==='T'?'Yes':'No'}</span>`:'';
  const calcHtml=(q.calc&&qno===4)?renderCalc(qno):'';
  const note=leg.notes&&leg.notes[qno];
  const hasDocFile=leg.docs&&leg.docs[qno];
  // attnQs: no "View Chart Note" button; regular doc questions: show it
  const docBtn=(!isAttn&&hasDocFile)?`<button class="doc-view-btn" onclick="openDoc(${qno})">📄 View Document</button>`:'';

  const aHtml=isEdit?`<div class="ansrow">
    <button class="abtn${a==='T'?' ay':''}" onclick="setAnsV3(${qno},'T')">Yes</button>
    <button class="abtn${a==='F'?' an':''}" onclick="setAnsV3(${qno},'F')">No</button>
  </div>`:'';

  // every question starts collapsed; the header badge shows where input is needed
  const qOpen=!!getWf().qOpen[qno];
  let bodyContent=`<p class="qfull">${escapeHtml(q.f)}</p>`;
  if(q.act) bodyContent+=`<p class="qfull" style="margin-top:2px">${escapeHtml(q.act)}</p>`;
  const cmt=leg.comments&&leg.comments[qno];
  if(cmt) bodyContent+=`<div class="qcomment">${escapeHtml(cmt)}</div>`;
  if(qno===4)bodyContent+=docBtn;
  bodyContent+=calcHtml;
  if(isEdit) bodyContent+=aHtml;
  const evCls=a==='T'?'qev-green':'qev-amber';
  if(isAttn&&note) bodyContent+=`<div class="qnote"><span class="nlbl">Note:</span> ${escapeHtml(note)}</div>`;
  else if(note&&!(q.auto&&q.ev)) bodyContent+=`<div class="${evCls}"><span class="evlbl">Evidence:</span> ${escapeHtml(note)}</div>`;
  if(q.auto&&q.ev) bodyContent+=`<div class="qev"><span class="evlbl">Evidence:</span> ${escapeHtml(q.ev)}</div>`;
  if(q.att) bodyContent+=`<div class="qnote"><span class="nlbl">Prescriber's answer:</span> ${escapeHtml(q.att)}</div>`;
  if(qno!==4)bodyContent+=docBtn;

  const hasDocStyle=(q.act||isAttn)?'qdoc':'';
  return`<div class="qcard ${hasDocStyle}" data-qno="${qno}">
    <div class="qhdr" onclick="toggleQ(${qno})">
      <span class="qn">Q${qno}</span><span class="qs">${escapeHtml(q.s)}</span>
      ${chip}${badge}<span class="qchev" id="chev-${qno}">${qOpen?'▲':'▼'}</span>
    </div>
    <div class="qbody" id="qb-${qno}" style="${qOpen?'':'display:none'}">${bodyContent}</div>
  </div>`;
}

function setAnsV3(qno,val){
  if(!['T','F'].includes(val)||!path(sa[curCase][curLeg]).steps.includes(qno))return;
  invalidateDecision();
  let ans=Object.assign({},sa[curCase][curLeg]);
  ans[qno]=val; ans=prune(ans); ans[qno]=val; ans=restoreInit(ans);
  sa[curCase][curLeg]=ans; getWf().verified={}; if(QM[qno]&&QM[qno].act)getWf().verified[qno]=true;
  renderWorkflow();
}
function cancelAllV3(){
  invalidateDecision();
  sa[curCase][curLeg]=Object.assign({},getLeg().initAns||{});
  getWf().calc={w0:'',w1:''}; getWf().verified={};
  renderWorkflow();
}
function s4ToggleEdit(){
  getWf().s4Edit=!getWf().s4Edit;
  renderWorkflow();
}

// ── STEP 1: Drug Verification ─────────────────────────────────────────────────
function renderStep1(c){
  const wf=getWf(), m=c.meta;
  const editHtml=wf.s1Edit?`
    <div class="wf-sub-section">
      <div class="wf-sub-ttl">Edit Drug</div>
      <div class="de-row"><div class="de-lbl">Drug name (as submitted)</div><div class="de-val">${escapeHtml(m.submittedDrug)}</div></div>
      <div class="de-row">
        <div class="de-lbl">Requested drug</div>
        <select class="de-sel" id="drug-sel">
          ${DRUG_LIST.map((d,i)=>`<option value="${i}"${d.label===m.requestedDrug?' selected':''}>${escapeHtml(d.label)}</option>`).join('')}
        </select>
      </div>
      <div style="margin-top:8px;display:flex;gap:7px">
        <button style="padding:5px 14px;background:var(--blue);color:#fff;border:none;border-radius:5px;font-size:11px;font-weight:600;cursor:pointer" onclick="s1SaveDrug()">Save</button>
        <button class="wf-toggle-btn" onclick="s1ToggleEdit()">Cancel</button>
      </div>
    </div>`:
    `<button class="wf-toggle-btn" style="margin-top:4px" onclick="s1ToggleEdit()">▾ Edit Drug</button>`;
  const same=m.requestedDrug===m.submittedDrug;
  const bodyHtml=`
    <div class="wf-insight" style="padding-top:12px">
      <div class="wf-insight-icon">✅</div>
      <div class="wf-insight-txt">${same?'Requested drug matches the submitted product.':`Requested drug <strong>set automatically</strong> to match the submitted product (<em>${escapeHtml(m.submittedDrug)}</em>).`}</div>
    </div>
    <div class="wf-badges">
      <span class="wf-badge wb-drug">Drug name: ${escapeHtml(m.submittedDrug)}</span>
      <span class="wf-badge wb-drug">Requested drug: ${escapeHtml(m.requestedDrug)}</span>
      <span class="wf-badge wb-ndc">NDC ${escapeHtml(m.ndc||'—')}</span>
      <span class="wf-badge wb-ndc">GPI/GCN ${escapeHtml(m.gpi||'—')}</span>
    </div>
    ${editHtml}`;
  return buildStepCard({
    n:1, title:'Drug Verification', sub:'',
    status:'✓ Verified', statusCls:'st-verified',
    open:wf.s1Open, doneCls:'wf-done', body:bodyHtml,
    toggleFn:'toggleStep(1)',
  });
}
function s1ToggleEdit(){getWf().s1Edit=!getWf().s1Edit;renderWorkflow();}
function s1SaveDrug(){
  const sel=el('drug-sel'), d=sel?DRUG_LIST[parseInt(sel.value)]:null;
  if(d){const m=getCase().meta; m.requestedDrug=d.label; m.drug=d.label; m.ndc=d.ndc||null;
    invalidateDecision();getWf().verified={};getWf().s2Ran=false;getWf().mcRunInput=null;}
  getWf().s1Edit=false; renderAll();
}

// ── STEP 2: Mock Claim Review ─────────────────────────────────────────────────
function renderMCOutcome(c){
  const cl=c.claim;
  const isBad=false; // reject code 75 (PA Required) = valid expected outcome — green
  const cls=isBad?'mc-outcome-reject':'mc-outcome-clear';
  const codeCls=isBad?'mc-code-reject':'mc-code-clear';
  const icon=isBad?'✗':'✓';
  return`<div class="mc-outcome ${cls}">
    <div class="mc-outcome-code ${codeCls}">${icon} Reject Code ${escapeHtml(cl.code)} — ${escapeHtml(cl.msg)}</div>
    <div class="mc-outcome-detail">${escapeHtml(cl.drug)}  ·  ${escapeHtml(cl.qty)}  ·  ${escapeHtml(cl.days)}-day supply  ·  Filled ${escapeHtml(cl.dt)}</div>
    <div class="mc-interp">PA is required. Continue working — do not turn away the member.</div>
  </div>`;
}
function renderStep2(c){
  const wf=getWf(), cl=c.claim, mcDef=wf.mcInput||MOCK_CLAIM_DEFS[c.id]||{};
  const sub='';
  const outcomeHtml=renderMCOutcome(c);
  const mcExpandBtn=`<button class="wf-toggle-btn" onclick="s2Toggle()">${wf.s2Open?'▴ Hide Manual Mock Claim':'▾ Run Manual Mock Claim'}</button>`;

  let mcFormHtml='';
  if(wf.s2Open){
    const resultHtml=wf.s2Ran?buildMCResult(c):'';
    mcFormHtml=`<div class="wf-sub-section">
      <div class="wf-sub-ttl">Manual Mock Claim</div>
      <div class="mc-form">
        <div class="mc-form-row">
          <div class="mcf mcf-wide"><div class="mcf-lbl">Drug Name</div><input class="mcf-inp" type="text" value="${escapeHtml(c.meta.drug)}" readonly style="background:var(--g50);color:var(--g600)"></div>
          <div class="mcf"><div class="mcf-lbl">NDC</div><input class="mcf-inp" type="text" value="${escapeHtml(c.meta.ndc||'')}" readonly style="background:var(--g50);color:var(--g600)"></div>
        </div>
        <div class="mc-form-row">
          <div class="mcf"><div class="mcf-lbl">Quantity</div><input class="mcf-inp" id="mc-qty" type="text" oninput="captureMockInput()" value="${escapeHtml(mcDef.qty||'4')}"></div>
          <div class="mcf"><div class="mcf-lbl">Days Supply</div><input class="mcf-inp" id="mc-days" type="text" oninput="captureMockInput()" value="${escapeHtml(mcDef.days||'28')}"></div>
          <div class="mcf"><div class="mcf-lbl">Pharmacy ID</div><input class="mcf-inp" id="mc-pharm" type="text" oninput="captureMockInput()" value="${escapeHtml(mcDef.pharmacyId||'2221113')}"></div>
        </div>
        <div class="mc-form-row">
          <div class="mcf"><div class="mcf-lbl">Fill Date</div><input class="mcf-inp" id="mc-fill" type="text" oninput="captureMockInput()" value="${escapeHtml(mcDef.fillDate||'')}"></div>
          <div class="mcf"><div class="mcf-lbl">Physician ID</div><input class="mcf-inp" id="mc-phys" type="text" oninput="captureMockInput()" value="${escapeHtml(mcDef.physicianId||'')}"></div>
          <div class="mcf"><div class="mcf-lbl">Product Selection Code</div>
            <select class="mcf-sel" id="mc-psc" onchange="captureMockInput()">
              <option value="0" ${(mcDef.psc||'0')==='0'?'selected':''}>0 — Not Specified</option>
              <option value="1" ${mcDef.psc==='1'?'selected':''}>1 — Substitution Allowed</option>
              <option value="2" ${mcDef.psc==='2'?'selected':''}>2 — Substitution Not Allowed</option>
              <option value="3" ${mcDef.psc==='3'?'selected':''}>3 — Substitution Allowed — Brand Dispensed</option>
            </select>
          </div>
        </div>
        <button class="mc-run-btn" onclick="runMockClaim()">Run Mock Claim</button><p id="mc-validation" class="demo-note" role="status"></p>
      </div>
      ${resultHtml}
    </div>`;
  }

  const statusTxt=wf.s2Ran?'✓ Mock Ran':'✓ PA Required';
  const statusCls=wf.s2Ran?'st-complete':'st-verified';
  const bodyHtml=`<div style="padding-top:12px">${outcomeHtml}</div>${mcExpandBtn}${mcFormHtml}`;

  return buildStepCard({
    n:3, title:'Mock Claim Review', sub,
    status:statusTxt, statusCls,
    open:wf.s2Card, doneCls:'wf-done', body:bodyHtml,
    toggleFn:'toggleStep(2)',
  });
}
function buildMCResult(c){
  const wf=getWf(), res=MC_RESULTS[c.id];
  if(!res)return'<p class="demo-note">No sample result configured for this case.</p>';
  const tabs=['msg','d30','d60','d90'];
  const tabLabels={msg:'Message',d30:'30 days',d60:'60 days',d90:'90 days'};
  const activeRes=res[wf.s2Tab]||res.msg;
  const tabHtml=tabs.map(t=>`<button class="mc-tab${wf.s2Tab===t?' act':''}" onclick="setMcTab('${t}')">${tabLabels[t]}</button>`).join('');
  return`<div class="mc-result-area" style="margin-top:10px">
    <div class="mc-tabs">${tabHtml}</div>
    <div class="mc-res-body">
      <p class="demo-note">Configured sample response · no claim transmitted</p>
      <div class="mc-res-lbl">Mock claim results — ${tabLabels[wf.s2Tab]} (reject code: ${escapeHtml(activeRes.code)})</div>
      <div class="mc-res-txt">${escapeHtml(activeRes.result)}</div>
      <div><div class="mc-settle-lbl">Settlement codes</div><div class="mc-settle">${escapeHtml(activeRes.settlement)}</div></div>
    </div>
  </div>`;
}
function s2Toggle(){getWf().s2Open=!getWf().s2Open;renderWorkflow();}
function captureMockInput(){
  if(!el('mc-qty'))return;
  const wf=getWf();
  wf.mcInput={};
  for(const [key,id] of Object.entries({qty:'mc-qty',days:'mc-days',pharmacyId:'mc-pharm',fillDate:'mc-fill',physicianId:'mc-phys',psc:'mc-psc'})){
    wf.mcInput[key]=el(id)?.value||'';
  }
}
function runMockClaim(){
  captureMockInput();
  const wf=getWf(), input=wf.mcInput;
  if(!input||!Number.isInteger(Number(input.qty))||Number(input.qty)<=0||!Number.isInteger(Number(input.days))||Number(input.days)<=0){
    el('mc-validation').textContent='Enter positive whole numbers for quantity and days supply.';return;
  }
  wf.mcRunInput={...input,drugName:getCase().meta.drug,ndc:getCase().meta.ndc};
  wf.s2Ran=true;wf.s2Open=true;renderWorkflow();
}
function setMcTab(t){getWf().s2Tab=t;renderWorkflow();}

// ── STEP 3: PA History ────────────────────────────────────────────────────────
function renderStep3(c){
  const wf=getWf(), td=TOOL_DATA[c.id]||{paHistory:[]};
  const hasDup=false;
  const dupPa='';
  let status, statusCls, alertHtml;
  if(hasDup){
    status='⚠ Duplicate Found'; statusCls='st-warning';
    alertHtml=`<div class="dup-alert" style="margin-top:12px">
      <div class="dup-ico">⚠️</div>
      <div>
        <div class="dup-ttl">Potential Duplicate PA: ${escapeHtml(dupPa)}</div>
        <div class="dup-detail">Prior approved PA for this member/drug/PAG is on file (approved 01/22/26). Verify this PA covers a new authorization period before proceeding.</div>
      </div>
    </div>`;
  }else{
    status='✓ Clear'; statusCls='st-verified';
    alertHtml=`<div class="ph-clear" style="padding-top:12px">${escapeHtml(c.phNote||'✓ No relevant prior PA history identified for this member and drug combination.')}</div>`;
  }
  const histTableHtml=wf.s3Exp?`<div style="overflow-x:auto;margin-top:8px">${buildPAHistStep(td.paHistory,c.id)}</div>`:'';
  const expBtn=`<div style="margin-top:8px"><button class="wf-toggle-btn" onclick="s3ToggleExp()">${wf.s3Exp?'▴ Hide PA History':'▾ View Full PA History'}</button></div>`;
  const bodyHtml=alertHtml+expBtn+histTableHtml;

  return buildStepCard({
    n:2, title:'PA History', sub:'',
    status, statusCls,
    open:wf.s3Open, doneCls:(hasDup?'':'wf-done'), body:bodyHtml,
    toggleFn:'toggleStep(3)',
  });
}
function buildPAHistStep(history=[],currentId){
  const rows=history.map(h=>{
    const cur=h.pa===currentId;
    const badge=h.outcome==='A'?'<span class="ph-a">✓ Approved</span>':h.outcome==='D'?'<span class="ph-d">✗ Denied</span>':'<span class="ph-r">● In Review</span>';
    return`<tr class="${cur?'ph-cur':''}"><td>${escapeHtml(h.pa)}${cur?' <span class="ph-cur-chip">current</span>':''}</td><td>${escapeHtml(h.drug)}</td><td>${escapeHtml(h.date)}</td><td>${badge}</td></tr>`;
  }).join('');
  return`<table class="ph-table"><thead><tr><th>PA Number</th><th>Drug</th><th>Date</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>`;
}
function s3ToggleExp(){getWf().s3Exp=!getWf().s3Exp;renderWorkflow();}

// ── STEP 4: Criteria Review ───────────────────────────────────────────────────
function renderStep4(c){
  const wf=getWf(), leg=getLeg();
  const ans=sa[curCase][curLeg];
  const sc=score(ans);
  const isEdit=wf.s4Edit;

  // Status: Scored Approval / Scored Denial / Unscored
  let status, statusCls;
  const pend=pendingVerify();
  if(sc==='A'&&pend.length){status='Scored Approval · needs verification'; statusCls='st-warning';}
  else if(sc==='A'){status='Scored Approval'; statusCls='st-complete';}
  else if(sc==='D'){status='Scored Denial'; statusCls='st-denied';}
  else{status='Input required'; statusCls='st-warning';}

  const{steps}=path(ans);
  let notices='';
  if(leg.fallout)notices+=`<div class="notice n-fallout"><span class="n-icon">⚡</span><span><strong>ePA Loop-2 Fallout:</strong> ${escapeHtml(leg.fallout)}</span></div>`;
  if(sc==='A'&&pend.length)notices+=`<div class="notice n-fallout"><span class="n-icon">⚠</span><span>Scores to <strong>Approval</strong> on the prescriber's answers. ${pend.map(q=>'Q'+q).join(', ')} still ${pend.length>1?'need':'needs'} your verification before you approve.</span></div>`;
  if(leg.dupNote)notices+=`<div class="notice n-dup"><span class="n-icon">ℹ</span><span>${escapeHtml(leg.dupNote)}</span></div>`;

  const qHtml=steps.length?steps.map(qno=>renderQCard(qno,ans,leg,isEdit)).join(''):`<p style="font-size:12px;color:var(--g400);font-style:italic;padding:6px 0">No criteria path available.</p>`;

  // Footer
  let footerHtml;
  if(isEdit){
    const scoreHtml=sc?`<hr class="score-sep"><div class="score-row"><span class="score-chip ${sc==='A'?'sc-a':'sc-d'}">${sc==='A'?'✓ Approval':'✗ Denial'}</span></div>`:'';
    footerHtml=`<div class="crit-foot">
      <div class="foot-btns">
        <button class="btn-c" onclick="cancelAllV3()">Cancel All</button>
        <button style="padding:7px 14px;background:var(--white);color:var(--blue);border:1.5px solid var(--blue);border-radius:6px;font-size:12px;font-weight:600;cursor:pointer" onclick="s4ToggleEdit()">Exit Edit</button>
      </div>
      ${scoreHtml}
    </div>`;
  }else{
    const scoreHtml=sc?`<hr class="score-sep"><div class="score-row"><span class="score-chip ${sc==='A'?'sc-a':'sc-d'}">${sc==='A'?'✓ Approval':'✗ Denial'}</span></div>`:'';
    footerHtml=`<div class="crit-foot">
      <div class="foot-btns">
        <button style="padding:7px 14px;background:var(--blue);color:#fff;border:none;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer" onclick="s4ToggleEdit()">Edit</button>
      </div>
      ${scoreHtml}
    </div>`;
  }

  const bodyHtml=`<div style="padding-top:4px"><span class="crit-nm">${escapeHtml(c.meta.name)}</span></div>${notices}<div class="qlist">${qHtml}</div>${footerHtml}`;

  return buildStepCard({
    n:4, title:'Criteria Review', sub:'',
    status, statusCls,
    open:wf.s4Open, doneCls:(sc&&!pend.length)?'wf-done':'wf-input', body:bodyHtml,
    toggleFn:'toggleStep(4)',
  });
}

// ── STEP 5: Notes ─────────────────────────────────────────────────────────────
function renderStep5(c){
  const wf=getWf();
  let status, statusCls, sub;
  if(wf.s5Gen){status='✓ Notes Generated';statusCls='st-complete';sub='';}
  else{status=wf.s5Text?'Notes entered':'○ Not Started';statusCls='st-pending';sub='';}
  const txt=wf.s5Text;
  const bodyHtml=`<div style="padding-top:12px">
    <div class="notes-wrap">
      <textarea class="notes-ta" id="notes-ta" maxlength="3000" placeholder="Enter or generate notes..." oninput="onNoteChange()">${escapeHtml(txt)}</textarea>
      <button class="gen-btn" onclick="genNoteV3()">Generate<br>Notes</button>
    </div>
    <div class="ncount" id="ncount">Characters remaining: ${3000-txt.length}</div>
  </div>`;

  return buildStepCard({
    n:5, title:'Notes', sub,
    status, statusCls,
    open:wf.s5Open, doneCls:wf.s5Gen?'wf-done':'', body:bodyHtml,
    toggleFn:'toggleStep(5)',
  });
}
function genNoteV3(){
  const c=getCase(), wf=getWf();
  const ans=sa[curCase][curLeg], sc=score(ans), {steps}=path(ans), pending=pendingVerify();
  const outcome=pending.length?'Pending verification':sc==='A'?'Approval supported':sc==='D'?'Denial — criteria not met':'Pending review';
  const leg=getLeg(), today=new Date().toLocaleDateString('en-US');
  const answered=steps.filter(q=>ans[q]!==undefined).map(q=>`Q${q}: ${ans[q]==='T'?'Yes':'No'}`).join('; ');
  const verified=steps.filter(q=>wf.verified[q]).map(q=>'Q'+q).join(', ')||'None';
  const pct=wf.verified[4]?calcPct():null;
  wf.s5Text=`Drug: ${c.meta.drug}\nDiagnosis: ${c.meta.dx||'Not provided'}\nAnswers: ${answered}\nManually verified: ${verified}${pct!==null?`\nWeight loss: ${pct.toFixed(1)}% (${wf.calc.w0} → ${wf.calc.w1} lbs)`:''}\nOutcome: ${outcome}${pending.length?' — '+pending.map(q=>'Q'+q).join(', '):''}\nInitials/Date: ${leg.rev||''} ${leg.role||''} ${today}\nLocal demo — no decision submitted.`.slice(0,3000);
  wf.s5Gen=true; wf.s5Open=true;
  renderWorkflow();
}
function onNoteChange(){
  const ta=el('notes-ta'); if(!ta)return;
  getWf().s5Text=ta.value;
  getWf().s5Gen=false;
  const badge=el('step-5')?.querySelector('.wf-status');
  if(badge){badge.textContent=ta.value?'Notes entered':'○ Not Started';badge.className='wf-status st-pending';}
  const cc=el('ncount'); if(cc)cc.textContent=`Characters remaining: ${3000-ta.value.length}`;
}

// ── STEP 6: Case Decision ─────────────────────────────────────────────────────
function renderStep6(c){
  const wf=getWf(), sc=score(sa[curCase][curLeg]);
  const recApprove=sc==='A';
  let status, statusCls, sub, bodyHtml;
  const pendQ=pendingVerify();
  if((sc===null||pendQ.length)&&wf.s6State==='idle'){
    return buildStepCard({
      n:6, title:'Case Decision', sub:'',
      status:'○ Waiting on verification', statusCls:'st-pending',
      open:wf.s6Open, doneCls:'', toggleFn:'toggleStep(6)',
      body:`<div class="ph-clear" style="padding-top:12px">${pendQ.length?`The criteria score to Approval on the prescriber's answers. Verify ${pendQ.map(q=>'Q'+q).join(', ')} in the Criteria Review first.`:'Finish the Criteria Review first. At least one question is still waiting on your input.'}</div>`,
    });
  }

  if(wf.s6State==='done'){
    const approved=wf.decision?.action==='approve';
    status=approved?'✓ Approved':'✓ Denied'; statusCls=approved?'st-approved':'st-denied'; sub='';
    bodyHtml=`<div class="dec-success">
      <div class="dec-success-ico">✅</div>
      <div class="dec-success-ttl">PA ${approved?'Approved':'Denied'} — Local Preview</div>
      <div class="dec-success-sub">Case ${escapeHtml(c.id)}: ${approved?'approval':'denial'} selected.<br>Export JSON to keep this result. No action was submitted to an external system.</div>
    </div>`;
  }else if(wf.s6State==='alt-done'){
    const labels={deny:'Denied',pending:'Set to Pending',rfi:'RFI Requested',internal:'Internal Denial',abort:'Aborted'};
    status=`✓ ${labels[wf.s6AltOpt]||'Closed'}`; statusCls='st-pending'; sub='';
    bodyHtml=`<div class="dec-alt-done">
      <div class="dec-alt-done-ttl">Case action completed: ${labels[wf.s6AltOpt]||wf.s6AltOpt}</div>
      <div class="dec-alt-done-sub">Case ${escapeHtml(c.id)}: local preview action recorded. Export JSON to keep the result; no external action was submitted.</div>
    </div>`;
  }else if(wf.s6State==='confirm'){
    status='● Pending Confirmation'; statusCls='st-active'; sub='';
    bodyHtml=`<div style="padding-top:12px"><div class="dec-rec ${recApprove?'':'dec-deny-rec'}">
      <div class="dec-rec-ico">${recApprove?'✅':'ℹ'}</div>
      <div class="dec-rec-body">
        <div class="dec-rec-ttl">Recommended: ${recApprove?'Approve':'Deny'}</div>
        <div class="dec-rec-sub">${recApprove?'All criteria verified.':'Criteria not fully met.'}</div>
      </div>
    </div>
    <div class="dec-confirm-box">
      <div class="dec-confirm-ttl">Please confirm the local ${recApprove?'approval':'denial'} for this PA.</div>
      <div class="dec-confirm-btns">
        <button class="dec-confirm-btn" onclick="decConfirmApprove()">Confirm ${recApprove?'Approval':'Denial'}</button>
        <button class="dec-back-btn" onclick="decGoBack()">Go Back</button>
      </div>
    </div></div>`;
  }else if(wf.s6State==='alt'){
    status='● Select Action'; statusCls='st-active'; sub='';
    const opts=[
      {k:'internal',lbl:'Internal Denial'},
      {k:'pending', lbl:'Set to Pending'},
      {k:'rfi',     lbl:'RFI'},
      {k:'deny',    lbl:'Deny'},
      {k:'abort',   lbl:'Abort'},
    ];
    const altBtns=opts.map(o=>`<button class="dec-alt-btn${wf.s6AltOpt===o.k?' selected':''}" onclick="decSelectAlt('${o.k}')">${o.lbl}</button>`).join('');
    const confirmBox=wf.s6AltOpt?`<div class="dec-alt-confirm-box">
      <div class="dec-alt-confirm-ttl">Confirm action: ${opts.find(o=>o.k===wf.s6AltOpt)?.lbl}</div>
      <div style="display:flex;gap:7px">
        <button class="dec-confirm-btn" style="background:var(--red)" onclick="decConfirmAlt()">Confirm</button>
        <button class="dec-back-btn" onclick="decGoBack()">Go Back</button>
      </div>
    </div>`:'';
    bodyHtml=`<div style="padding-top:12px"><div class="dec-rec ${recApprove?'':'dec-deny-rec'}">
      <div class="dec-rec-ico">${recApprove?'✅':'⚠️'}</div>
      <div class="dec-rec-body"><div class="dec-rec-ttl">Recommended: ${recApprove?'Approve':'Deny'}</div></div>
    </div>
    <div class="dec-q">Select an alternative close option:</div>
    <div class="dec-alt-list">${altBtns}</div>${confirmBox}</div>`;
  }else{
    // idle
    status='● Active'; statusCls='st-active'; sub='';
    bodyHtml=`<div style="padding-top:12px"><div class="dec-rec ${recApprove?'':'dec-deny-rec'}">
      <div class="dec-rec-ico">${recApprove?'✅':'⚠️'}</div>
      <div class="dec-rec-body">
        <div class="dec-rec-ttl">Recommended decision: ${recApprove?'Approve':'Deny'}</div>
        <div class="dec-rec-sub">${recApprove?'All criteria verified. Documentation complete. Approval is supported.':'Criteria not fully met per documentation on file.'}</div>
      </div>
    </div>
    <div class="dec-q">Would you like to ${recApprove?'approve':'deny'} this PA?</div>
    <div class="dec-btns">
      <button class="dec-yes" onclick="decYes()">Yes</button>
      <button class="dec-no" onclick="decNo()">No — Other Options</button>
    </div></div>`;
  }

  return buildStepCard({
    n:6, title:'Case Decision', sub,
    status, statusCls,
    open:wf.s6Open,
    doneCls:(wf.s6State==='done'||wf.s6State==='alt-done')?'wf-done':'wf-active',
    body:bodyHtml, toggleFn:'toggleStep(6)',
  });
}
function canDecide(){return ['A','D'].includes(score(sa[curCase][curLeg]))&&!pendingVerify().length;}
function decYes(){if(!canDecide())return;getWf().s6State='confirm';renderWorkflow();}
function decNo(){if(!canDecide())return;getWf().s6State='alt';getWf().s6AltOpt=null;renderWorkflow();}
function recordDecision(action){
  const wf=getWf();
  wf.decision={action,recordedAt:new Date().toISOString(),score:score(sa[curCase][curLeg]),answers:{...sa[curCase][curLeg]},verified:{...wf.verified}};
}
function decConfirmApprove(){
  if(!canDecide()||getWf().s6State!=='confirm')return;
  recordDecision(score(sa[curCase][curLeg])==='A'?'approve':'deny');getWf().s6State='done';renderWorkflow();
}
function decGoBack(){getWf().s6State='idle';getWf().s6AltOpt=null;renderWorkflow();}
function decSelectAlt(opt){if(getWf().s6State!=='alt'||!['internal','pending','rfi','deny','abort'].includes(opt))return;getWf().s6AltOpt=opt;renderWorkflow();}
function decConfirmAlt(){if(!canDecide()||getWf().s6State!=='alt'||!getWf().s6AltOpt)return;recordDecision(getWf().s6AltOpt);getWf().s6State='alt-done';renderWorkflow();}

// ── BUILD STEP CARD ───────────────────────────────────────────────────────────
function buildStepCard({n,title,sub,status,statusCls,open,doneCls,body,toggleFn}){
  const openBody=open!==false;
  return`<div class="wf-step ${doneCls||''}" id="step-${n}">
    <div class="wf-step-hdr" onclick="${toggleFn}">
      <div class="wf-step-left">
        <div class="wf-step-num">${n}</div>
        <div class="wf-step-meta">
          <div class="wf-step-title">${title}</div>
          ${sub?`<div class="wf-step-sub">${sub}</div>`:''}
        </div>
      </div>
      <div class="wf-step-right">
        <span class="wf-status ${statusCls}">${status}</span>
        <span class="wf-chev">${openBody?'▲':'▼'}</span>
      </div>
    </div>
    <div class="wf-step-body" id="step-${n}-body" style="${openBody?'':'display:none'}">${body}</div>
  </div>`;
}

// ── STEP TOGGLE ───────────────────────────────────────────────────────────────
function toggleStep(n){
  const wf=getWf();
  const keys={1:'s1Open',2:'s2Card',3:'s3Open',4:'s4Open',5:'s5Open',6:'s6Open'};
  const k=keys[n]; if(!k)return;
  wf[k]=!wf[k];
  renderWorkflow();
}

// ── RENDER WORKFLOW ───────────────────────────────────────────────────────────
function renderWorkflow(){
  const c=getCase();
  const container=el('wf-steps'); if(!container)return;
  container.innerHTML=
    renderStep1(c)+
    renderStep3(c)+
    renderStep2(c)+
    renderStep4(c)+
    renderStep5(c)+
    renderStep6(c);
  document.querySelectorAll('.wf-step-hdr,.qhdr').forEach(node=>{
    node.setAttribute('role','button');node.tabIndex=0;
    const body=node.nextElementSibling;
    node.setAttribute('aria-expanded',String(body?.style.display!=='none'));
  });
}

// ── NAVIGATION ────────────────────────────────────────────────────────────────
function selectCase(idx){
  curCase=parseInt(idx); curLeg=0;
  renderAll();
}
function selectLeg(idx){
  curLeg=idx;
  renderAll();
}

// ── RENDER ALL ────────────────────────────────────────────────────────────────
function renderAll(){
  renderCaseSelector();
  updateTop(); syncDemoSel(); renderBarRole(); renderStrip(); renderLegBar();
  renderMember(); renderPAInfo(); renderMemberCenter();
  renderWorkflow();
}
function renderCaseSelector(){
  if(CASES.length<=1)return;
  let select=el('demo-sel');
  if(!select){
    select=document.createElement('select');select.id='demo-sel';select.className='demo-sel';
    select.setAttribute('aria-label','Select case');
    CASES.forEach((c,index)=>{const option=document.createElement('option');option.value=String(index);option.textContent=c.id;select.append(option);});
    select.addEventListener('change',()=>selectCase(select.value));
    document.querySelector('.bar-right').prepend(select);
  }
}

function reviewOutput(){
  const c=getCase(), wf=getWf(), answers=sa[curCase][curLeg], result=path(answers);
  return {
    schemaVersion:1,mode:'local-demo',exportedAt:new Date().toISOString(),caseId:c.id,legIndex:curLeg,
    role:getLeg().role,reviewer:getLeg().rev,drug:{submitted:c.meta.submittedDrug,requested:c.meta.requestedDrug,ndc:c.meta.ndc},
    urgent:!!c.meta.urgent,answers:{...answers},questionPath:result.steps,score:result.terminal,
    pendingVerification:pendingVerify(),verified:{...wf.verified},weightCalculation:{...wf.calc,percentLoss:calcPct()},
    mockClaim:{input:wf.mcInput||MOCK_CLAIM_DEFS[c.id]||{},lastRunInput:wf.mcRunInput,sampleResult:wf.s2Ran?(MC_RESULTS[c.id]?.[wf.s2Tab]||null):null},
    notes:wf.s5Text,decision:wf.decision
  };
}
function exportReview(){
  const blob=new Blob([JSON.stringify(reviewOutput(),null,2)+'\n'],{type:'application/json'});
  const url=URL.createObjectURL(blob), link=document.createElement('a');
  link.href=url;link.download=`review-${String(getCase().id).replace(/[^\w-]/g,'_')}.json`;
  document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
window.startApp = ()=>{
  renderAll();
  window.addEventListener('resize',updateTop);
  document.querySelectorAll('.lsec-hdr[onclick]').forEach(node=>{node.tabIndex=0;node.setAttribute('role','button');});
  document.addEventListener('keydown',event=>{
    if(event.key==='Escape'){closeDoc();closeTool();}
    if((event.key==='Enter'||event.key===' ')&&event.target.matches('.wf-step-hdr,.qhdr,.lsec-hdr[onclick]')){
      event.preventDefault();event.target.click();
    }
  });
};
