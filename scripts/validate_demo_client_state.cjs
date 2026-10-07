// Exact production functions, mocked I/O only. No DOM browser or network claims.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../webapp/app.js'), 'utf8');
function fn(name) {
  const start = source.indexOf('function '+name+'(');
  assert(start >= 0, name);
  const begin = source.slice(start-6,start) === 'async ' ? start-6 : start;
  return source.slice(begin, source.indexOf('\n}', start)+2);
}
function context() {
  const statuses = [];
  const c = {statuses, api:{getLogs:async()=>[],getSettings:async()=>({}),getSystemMessageDefaults:async()=>({}),getSavedScopes:async()=>[],getTriageDashboard:async()=>({totals:{messages:8}})},
    renderLogs(){}, fillSettings(){}, renderTriageScopeOptions(){}, renderTriageDashboard(){}, renderTriageDashboardError(){},
    updateActionScopePreview(){}, hideActionConfirm(){}, collectTriageDashboardFilters:()=>({}),
    setStatus:(text,isError)=>statuses.push({text,isError:!!isError}), isolatedDemo:true,activeSafeMode:true,applyInFlight:false,dashboardRequestVersion:0,
    document:{getElementById:()=>({})}};
  c.setMutationBusy = busy => { c.applyInFlight = busy; };
  vm.createContext(c);
  vm.runInContext(['refreshTriageScopes','refreshTriageDashboard','loadInitialData','refreshAfterMutation','runUndoActions'].map(fn).join('\n'),c);
  return c;
}
(async()=>{
  let c=context(); c.api.getTriageDashboard=async()=>{throw Error('Synthetic dashboard failure');};
  assert.equal(await c.loadInitialData(),false);
  assert(c.statuses.at(-1).isError); assert(!c.statuses.some(s=>s.text.includes('Sample inbox ready')));
  c=context();c.api.getSavedScopes=async()=>{throw Error('Synthetic scope failure');};
  assert.equal(await c.loadInitialData(),false);assert(c.statuses.at(-1).isError);
  c=context();assert.equal(await c.loadInitialData(),true);assert(!c.statuses.at(-1).isError);
  c=context();c.api.getTriageDashboard=async()=>{throw Error('Synthetic view failure');};
  assert.equal(await c.refreshAfterMutation('Undo completed.'),false);
  assert(c.statuses.at(-1).isError);assert(c.statuses.at(-1).text.includes('Undo completed.'));assert(c.statuses.at(-1).text.includes('Dashboard refresh failed'));
  c=context();let calls=0,release; c.api.undo=()=>{calls++;return new Promise(r=>{release=r;});};
  const first=c.runUndoActions();await c.runUndoActions();assert.equal(calls,1);
  release({undoCompleted:true,warning:'Undo completed. Rebuild sample index.'});await first;
  assert(c.statuses.at(-1).isError);assert.equal(c.applyInFlight,false);
  for (const triage of [false,true]) {
    for (const error of [false,true]) {
      const elements=new Map(), rendered=[], statuses=[];
      const el=id=>{ if(!elements.has(id)) elements.set(id,{addEventListener(type,handler){this[type]=handler;},closest(){return {hidden:false};},click(){}}); return elements.get(id); };
      let settle, finishReset;
      const c={isolatedDemo:true,applyInFlight:false,currentJobId:'before-reset',currentMessages:[{id:'demo-001'}],selectedMessageId:null,currentMessageDetail:null,latestMessageDetailRequest:0,currentTriageSelectedMessageId:null,latestTriageMessageDetailRequest:0,dashboardRequestVersion:0,currentTriageDashboard:{},summaryCard:{dataset:{}},
        api:{getMessageDetail:()=>new Promise((resolve,reject)=>{settle=error?()=>reject(Error('Late failure')):()=>resolve({id:'demo-001',body:'PRE-RESET BODY'});}),resetDemo:()=>new Promise(resolve=>{finishReset=resolve;})},
        document:{getElementById:el,querySelector:()=>el('tab'),addEventListener(){}},scopeActionEmail:el('email'),
        renderMessages(m){c.currentMessages=m;},updateDigestMetrics(){},updateActionScopePreview(){},updateBottomStatusBar(){},getMessageListItem:()=>({subject:'Sample'}),findTriageMessageSample:()=>({subject:'Sample'}),parseMailbox:()=>({name:'Sample',address:'sample@example.com'}),renderMessageDetail:(d)=>rendered.push(d),renderTriageMessageDetail:(d)=>rendered.push(d),renderTriageMessagePlaceholder:()=>rendered.push(null),setStatus:m=>statuses.push(m),
        setMutationBusy:b=>{c.applyInFlight=b;},hideActionConfirm(){},cancelSummary(){},confirm:()=>true,summaryText:{},jobIdLabel:{},setActionButtons(){},hideActionToast(){},loadInitialData:async()=>true};
      c.api.getMailIndexMessage=c.api.getMessageDetail;
      vm.createContext(c);vm.runInContext(['selectMessage','selectTriageMessage','clearCurrentWorkspaceState','setupDemo'].map(fn).join('\n'),c);c.setupDemo();
      const request=triage?c.selectTriageMessage('demo-001'):c.selectMessage('demo-001');
      const reset=el('demo-reset').click({target:el('demo-reset')});
      // Invalidate at acceptance, even while the reset HTTP response is held.
      assert.equal(c.selectedMessageId,null);assert.equal(c.currentTriageSelectedMessageId,null);
      assert(c.latestMessageDetailRequest>0);assert(c.latestTriageMessageDetailRequest>0);
      finishReset({indexRefreshed:true});await reset;
      const count=rendered.length,lastStatus=statuses.at(-1);
      settle();await request;
      assert.equal(rendered.length,count);assert.equal(c.currentMessageDetail,null);
      assert.equal(statuses.at(-1),lastStatus);assert.equal(c.currentJobId,null);
    }
  }
  console.log('9 client-state regressions passed (mocked I/O, no network)');
})().catch(error=>{console.error(error);process.exitCode=1;});
