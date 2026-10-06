// Exact production functions, mocked I/O only. No DOM browser or network claims.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../webapp/app.js'), 'utf8');
function fn(name) {
  const start = source.indexOf('async function '+name+'(');
  assert(start >= 0, name);
  return source.slice(start, source.indexOf('\n}', start)+2);
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
  console.log('5 client-state regressions passed (mocked I/O, no network)');
})().catch(error=>{console.error(error);process.exitCode=1;});
