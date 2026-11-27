/* ---- 화면(DOM)과 무관한 순수 함수 모음 ----
   브라우저에서는 전역 DocsLib 로, Node 테스트에서는 require("site_src/lib.js") 로 쓴다.
   DOM 을 만지는 코드는 app.js / search.js / highlight.js 에 있고, 판단과 계산은 여기에 둔다. */
var DocsLib=(function(){

/* ---- 앵커: Python 의 docs_markdown.anchor_key 와 같은 규칙이어야 한다 (URL 디코딩, 소문자, 글자·숫자만) ---- */
function anchorKey(s){try{s=decodeURIComponent(s)}catch(e){}return s.toLowerCase().replace(/[^\p{L}\p{N}]/gu,"")}

/* ---- 사이드바 트리: 노드는 {p:경로} 또는 {g:이름, c:[노드...]} ---- */
function navFirst(n){if(n.p)return n.p;for(var i=0;i<n.c.length;i++){var r=navFirst(n.c[i]);if(r)return r}return ""}
function navHas(n,p){if(n.p)return n.p===p;return n.c.some(function(c){return navHas(c,p)})}
function labelMatches(label,q){return !q||label.toLowerCase().indexOf(q)>=0}

/* ---- 우측 목차 ---- */
function tocClass(tag){return tag==="H3"?"l3":"l2"}
/* 각 제목의 화면 위쪽 좌표 tops 에서 현재 읽는 제목의 순번: limit 이하로 올라온 마지막 것. 맨 아래까지 내렸으면 마지막. */
function currentIndex(tops,limit,atBottom){var cur=0;for(var i=0;i<tops.length;i++){if(tops[i]<=limit)cur=i;else break}
 if(atBottom)cur=tops.length-1;return cur}

/* ---- 본문 검색: 문서는 {t:제목, x:본문, h:[[제목글자,id]...], p:경로} ---- */
function prepare(docs){docs.forEach(function(d){d.lt=d.t.toLowerCase();d.lx=d.x.toLowerCase()});return docs}
function searchTerms(raw){var q=raw.trim().toLowerCase();return q.length<2?[]:q.split(/\s+/).filter(Boolean)}
function countOccurrences(h,t){var n=0,i=0;while(n<20&&(i=h.indexOf(t,i))>=0){n++;i+=t.length}return n}
/* 모든 검색어가 제목·헤딩·본문 중 어딘가에 있어야 한다. 없으면 -1, 있으면 점수(제목 100, 헤딩 20, 본문 등장 횟수). */
function scoreDoc(d,terms){var score=0;
 for(var i=0;i<terms.length;i++){var t=terms[i],inT=d.lt.indexOf(t)>=0,inX=d.lx.indexOf(t)>=0,
  inH=d.h.some(function(h){return h[0].toLowerCase().indexOf(t)>=0});
  if(!inT&&!inX&&!inH)return -1;score+=(inT?100:0)+(inH?20:0)+countOccurrences(d.lx,t)}
 return score}
function rankDocs(docs,terms){var hits=[];
 docs.forEach(function(d){var s=scoreDoc(d,terms);if(s>=0)hits.push({d:d,s:s})});
 hits.sort(function(a,b){return b.s-a.s});return hits}
/* 검색어가 들어 있는 첫 헤딩([글자,id]), 없으면 undefined */
function pickHeading(d,terms){return d.h.filter(function(x){return terms.some(function(t){return x[0].toLowerCase().indexOf(t)>=0})})[0]}
/* 본문에서 검색어가 처음 나오는 위치, 없으면 -1 */
function firstMatchIndex(d,terms){var i=-1;terms.forEach(function(t){var k=d.lx.indexOf(t);if(k>=0&&(i<0||k<i))i=k});return i}
/* text 를 [[강조 여부(0|1), 글자], ...] 조각으로 나눈다 */
function markSegments(text,terms){var low=text.toLowerCase(),pos=0,out=[];
 while(pos<text.length){var best=-1,bl=0;
  terms.forEach(function(t){var i=low.indexOf(t,pos);if(i>=0&&(best<0||i<best)){best=i;bl=t.length}});
  if(best<0){out.push([0,text.slice(pos)]);break}
  if(best>pos)out.push([0,text.slice(pos,best)]);
  out.push([1,text.slice(best,best+bl)]);pos=best+bl}
 return out}

/* ---- 코드 구문 강조 (규칙 기반) ---- */
var C={c:"#",kw:"if then else elif fi for while do done case esac in function return export local echo cd ls cat grep git npm npx pip python python3 node claude curl mkdir rm cp mv sudo exit set unset source alias read test true false"};
var JSK="const let var function return if else for while do switch case break continue new class extends import export from default async await try catch finally throw typeof instanceof in of this null undefined true false void yield static interface type enum implements public private readonly";
var HL={bash:C,sh:C,shell:C,zsh:C,console:C,
 json:{kw:"true false null",key:1},jsonc:{c:"//",kw:"true false null",key:1},
 python:{c:"#",kw:"def class return if elif else for while in not and or is import from as with try except finally raise pass break continue lambda yield None True False async await self print",tq:1},
 yaml:{c:"#",kw:"true false null yes no"},yml:{c:"#",kw:"true false null yes no"},toml:{c:"#",kw:"true false"},
 powershell:{c:"#",kw:"if else elseif foreach for while function return param switch try catch finally throw $true $false $null"},
 javascript:{c:"//",kw:JSK,bt:1},js:{c:"//",kw:JSK,bt:1},typescript:{c:"//",kw:JSK,bt:1},ts:{c:"//",kw:JSK,bt:1},jsx:{c:"//",kw:JSK,bt:1},tsx:{c:"//",kw:JSK,bt:1}};
HL.ps1=HL.powershell;HL.py=HL.python;
function langConfig(name){return HL[(name||"").toLowerCase()]}
function highlightRegex(cfg){var cm=[];
 if(cfg.c==="#")cm.push("(?<![^\\s])#[^\\n]*");
 if(cfg.c==="//")cm.push("//[^\\n]*","/\\*[\\s\\S]*?\\*/");
 var Q3='"'+'"'+'"',S3="'"+"'"+"'",st=[];if(cfg.tq)st.push(Q3+"[\\s\\S]*?"+Q3,S3+"[\\s\\S]*?"+S3);
 st.push('"(?:[^"\\\\\\n]|\\\\.)*"',"'(?:[^'\\\\\\n]|\\\\.)*'");if(cfg.bt)st.push("`(?:[^`\\\\]|\\\\.)*`");
 return new RegExp("("+(cm.join("|")||"(?!)")+")|("+st.join("|")+")|(\\b\\d+(?:\\.\\d+)?\\b)|([$A-Za-z_][\\w$-]*)","g")}
/* text 를 [[클래스|null, 글자], ...] 조각으로 나눈다. 클래스: tk-c 주석, tk-s 문자열, tk-key JSON 키, tk-n 숫자, tk-k 키워드 */
function tokenize(text,cfg){var kw={};cfg.kw.split(" ").forEach(function(w){kw[w]=1});
 var r=highlightRegex(cfg),pos=0,m,out=[];
 while((m=r.exec(text))){if(m.index>pos)out.push([null,text.slice(pos,m.index)]);
  if(m[1])out.push(["tk-c",m[0]]);
  else if(m[2]){var isKey=cfg.key&&/^\s*:/.test(text.slice(r.lastIndex,r.lastIndex+20));out.push([isKey?"tk-key":"tk-s",m[0]])}
  else if(m[3])out.push(["tk-n",m[0]]);
  else if(kw[m[0]])out.push(["tk-k",m[0]]);else out.push([null,m[0]]);
  pos=r.lastIndex;if(m[0].length===0)r.lastIndex++}
 if(pos<text.length)out.push([null,text.slice(pos)]);
 return out}

return {anchorKey:anchorKey,navFirst:navFirst,navHas:navHas,labelMatches:labelMatches,tocClass:tocClass,currentIndex:currentIndex,
 prepare:prepare,searchTerms:searchTerms,countOccurrences:countOccurrences,scoreDoc:scoreDoc,rankDocs:rankDocs,
 pickHeading:pickHeading,firstMatchIndex:firstMatchIndex,markSegments:markSegments,
 langConfig:langConfig,highlightRegex:highlightRegex,tokenize:tokenize}
})();
if(typeof module!=="undefined"&&module.exports)module.exports=DocsLib;
