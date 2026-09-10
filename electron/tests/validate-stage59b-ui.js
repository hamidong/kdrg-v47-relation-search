'use strict';
const assert = require('node:assert/strict'); const fs=require('node:fs'); const path=require('node:path');
const root=path.resolve(__dirname,'..'); const html=fs.readFileSync(path.join(root,'renderer/index.html'),'utf8'); const app=fs.readFileSync(path.join(root,'renderer/app.js'),'utf8'); const fmt=fs.readFileSync(path.join(root,'renderer/ui-formatters.js'),'utf8');
let pass=0;const fail=[];function check(n,f){try{f();pass+=1}catch(e){fail.push(`${n}: ${e.message}`)}}
check('public type AADRG',()=>{assert.match(html,/value="AADRG">AADRG/);assert.doesNotMatch(html,/<option value="ADRG">/)});
check('MDC dynamic',()=>{assert.match(app,/function populateMdcFilter/);assert.doesNotMatch(html,/value="24">MDC 24/);assert.doesNotMatch(html,/value="25">MDC 25/)});
check('history',()=>{assert.match(html,/id="detail-back"/);assert.match(app,/historyStack/);assert.match(app,/relation-detail/);assert.match(app,/restoreWindowScroll/);assert.doesNotMatch(app,/openFirst/)});
check('AADRG detail',()=>{assert.match(app,/function renderAadrgDetail/);assert.match(app,/'관련 코드'/);assert.match(app,/renderUserConditionSummary\(detail\)/);assert.match(app,/renderUserConditionTables\(detail\)/)});
check('pretty condition',()=>{assert.match(app,/function prettyConditionLines/);assert.match(app,/condition-pretty-expression/)});
check('relation AADRG',()=>{assert.match(app,/관계검색 AADRG/);assert.match(app,/makeBadge\('AADRG'\)/);assert.match(app,/AADRG 상세 보기/);assert.doesNotMatch(app,/ADRG 전체 상세/)});
check('TABLE technical hidden',()=>{assert.doesNotMatch(app,/TABLE 기술 상세/);assert.doesNotMatch(app,/table-technical-button/);assert.doesNotMatch(app,/내부 ID \$\{tableId\}/)});
check('CODE detail AADRG centered',()=>{const a=app.indexOf('function renderCodeDetail');const b=app.indexOf('\nfunction ',a+20);const body=app.slice(a,b>a?b:a+4000);assert.match(body,/'관련 AADRG'/);assert.doesNotMatch(body,/'관련 ADRG'/);assert.doesNotMatch(body,/'포함 TABLE'/);assert.doesNotMatch(body,/'연결 TABLE'/)});
check('formatter public counts',()=>assert.match(fmt,/const ordered = \['CODE', 'AADRG'\]/));
console.log(`stage59_ui: ${pass} PASS / ${fail.length} FAIL`);if(fail.length){fail.forEach(x=>console.log('- '+x));process.exitCode=1;}
