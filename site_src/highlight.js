/* ---- 코드 구문 강조 (규칙 기반). 토큰 나누기는 lib.js 의 tokenize ---- */
(function(){
function span(parent,cls,text){var s=document.createElement("span");s.className=cls;s.textContent=text;parent.appendChild(s)}
document.querySelectorAll("pre[data-lang]").forEach(function(pre){var cfg=DocsLib.langConfig(pre.dataset.lang),code=pre.querySelector("code");
 if(!cfg||!code)return;var text=code.textContent;if(text.length>30000)return;
 var out=document.createDocumentFragment();
 DocsLib.tokenize(text,cfg).forEach(function(t){if(t[0])span(out,t[0],t[1]);else out.appendChild(document.createTextNode(t[1]))});
 code.textContent="";code.appendChild(out)});
})();
