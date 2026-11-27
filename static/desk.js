"use strict";
const $ = id => document.getElementById(id);
const labels = {archived:"Archived",superseded:"Superseded",checking:"Checking", pending:"Awaiting decision", approved:"Approved", rejected:"Rejected", clarification:"Clarification requested", blocked:"Policy block", failed:"Review failed"};
const verdicts = {aligned:"Requirements match", conflict:"Instructions conflict", missing:"A requirement is missing", unclear:"Meaning is unclear", off_task:"Decision outside the task", sensitive:"Credential detected", suspicious:"Instruction override detected", unavailable:"Review unavailable"};
let idToken = "", editing = null;
let config, selected = null, rows = [], revision = 0, loading = false;

async function api(path, body, headers = {}) {
  const options = body === undefined ? {} : {method:"POST", headers:{"Content-Type":"application/json", ...headers}, body:JSON.stringify(body)};
  if (idToken) options.headers = {...options.headers, Authorization:"Bearer " + idToken};
  const response = await fetch(path, options);
  if (response.status === 401 && config?.firebase) {idToken = ""; loginView(true);}
  const result = await response.json();
  if (!response.ok && result.state !== "failed") throw Error(result.error || "The service is unavailable. Please retry.");
  return result;
}
const notice = message => { $("notice").textContent = message; };
function bind(id, action) {
  $(id).onclick = async () => { try { await action(); } catch (e) { notice(e.message); } };
}
function packetPath(id) { return "/api/reviews/" + id; }
function drawQueue() {
  const visible = rows.filter(r => !$("filter").value || r.state === $("filter").value);
  $("count").textContent = visible.length;
  const buttons = visible.map(r => {
    const btn = document.createElement("button"), meta = document.createElement("small");
    btn.className = "queueitem"; btn.setAttribute("aria-current", String(selected?.id === r.id));
    btn.textContent = r.reference;
    meta.textContent = labels[r.state] + (r.revision ? " · v" + r.revision : ""); btn.append(meta);
    btn.onclick = () => openPacket(r.id).catch(e => notice(e.message));
    return btn;
  });
  if (!buttons.length) {
    const empty = document.createElement("p"); empty.className = "empty";
    empty.textContent = rows.length ? "No reviews in this view." : "Submitted handoffs will appear here.";
    buttons.push(empty);
  }
  $("queue").replaceChildren(...buttons);
}
function show(r) {
  selected = r; $("compose").hidden = true; $("report").hidden = false;
  $("title").textContent = r.reference; $("state").textContent = labels[r.state];
  $("stamp").textContent = (r.revision ? "Revision " + r.revision : "Prior review") + " · " + new Date(r.updated*1000).toLocaleString() + (r.decision_by ? " · " + r.decision_by : "");
  const f = r.finding || {};
  $("engine").textContent = r.engine || "Review in progress"; $("verdict").textContent = verdicts[f.status] || "Checking handoff";
  $("reason").textContent = f.reason || "The result will appear here automatically.";
  $("verdict").parentElement.dataset.tone = f.status === "aligned" ? "pass" : "hold";
  $("evidence").hidden = !f.source_quote && !f.handoff_quote;
  $("sq").textContent = f.source_quote || "—"; $("hq").textContent = f.handoff_quote || "—";
  $("fullsource").textContent = r.source; $("fullhandoff").textContent = r.handoff; $("full").hidden = !r.source;
  $("history").replaceChildren(...(r.events || []).map(event => {
    const li = document.createElement("li");
    li.textContent = new Date(event.at*1000).toLocaleTimeString() + " · " + event.label;
    return li;
  }));
  const bands = ["Low", "Ambiguous", "Incomplete or off task", "High", "Critical"];
  $("score").textContent = r.risk_score == null ? "Unscored" : r.risk_score + "/4 · " + bands[r.risk_score];
  $("recommendation").textContent = ["superseded","archived"].includes(r.state) ? "Release unavailable" : r.recommended_action;
  const checks = f.additional_findings || [];
  $("otherFindings").hidden = !checks.length;
  $("checks").replaceChildren(...checks.map(item => {
    const panel = document.createElement("details");
    for (const [tag,text] of [["summary",verdicts[item.status]],["p",item.reason],["h4","Source evidence"],["blockquote",item.source_quote],["h4","Handoff evidence"],["blockquote",item.handoff_quote]]) {
      const node = document.createElement(tag); node.textContent = text; panel.append(node);
    }
    return panel;
  }));
  $("controls").hidden = r.state !== "pending"; $("tokenLabel").hidden = !config.protected;
  for (const button of document.querySelectorAll("[data-action]")) {
    const rec = {Approve:"approved", Reject:"rejected"}[r.recommended_action] || "clarification";
    button.classList.toggle("primary",button.dataset.action === rec);
  }
  $("run").hidden = r.state !== "approved" || ![config.source,config.examples["Corrected wording"],config.examples["Changed instruction"]].includes(r.handoff);
  $("revise").hidden = !r.source || r.state === "superseded"; $("simulation").textContent = ""; drawQueue();
}
async function openPacket(id) {
  const sequence = ++revision;
  const r = await api(packetPath(id));
  if (sequence === revision) {notice(""); show(r);}
}
function compose(r) {
  ++revision; selected = null; $("report").hidden = true; $("compose").hidden = false;
  resetFiles();
  editing = r?.revision ? r : null;
  $("reference").readOnly = Boolean(editing);
  $("receiverUid").value = r?.receiver_uid || "";
  $("options").open = false;
  $("example").value = r ? "Custom" : "Deprecated API alias";
  $("source").value = r ? r.source : config.alias_source;
  $("handoff").value = r ? r.handoff : config.examples["Deprecated API alias"];
  $("reference").value = r ? r.reference : "API compatibility"; notice(""); drawQueue();
}
function resetFiles() {
  $("sourceFile").value = ""; $("handoffFile").value = "";
}
function selectExample() {
  const name = $("example").value;
  resetFiles(); notice("");
  if (name === "Custom") return;
  const alias = name === "Deprecated API alias";
  $("source").value = alias ? config.alias_source : config.source;
  if (!editing) $("reference").value = alias ? "API compatibility" : "Payment retries";
  $("handoff").value = config.examples[name];
}
async function importConversation(field) {
  const input = $(field + "File"), file = input.files[0];
  if (!file) return;
  $(field).value = ""; $("example").value = "Custom";
  if (file.size > 56003) throw Error("Choose a conversation of at most 14,000 characters.");
  const bytes = await file.arrayBuffer();
  if (input.files[0] !== file) return;
  let text;
  try { text = new TextDecoder("utf-8",{fatal:true}).decode(bytes).replace(/\r\n?/g,"\n"); }
  catch { throw Error("Save the conversation as UTF-8 text and upload again."); }
  if (!text.trim() || text.includes("\0") || text.length > 14000)
    throw Error("Choose a nonempty text conversation of at most 14,000 characters.");
  $(field).value = text; notice("");
}
async function refresh() {
  if (loading) return; loading = true;
  try {
    rows = await api("/api/reviews"); drawQueue();
    const latest = selected && rows.find(r => r.id === selected.id);
    if (latest && latest.updated !== selected.updated) await openPacket(latest.id);
  } finally { loading = false; }
}
function loginView(visible) {
  $("testDesk").hidden = visible;
  if (visible) $("testResult").hidden = true;
  $("login").hidden = !visible; $("workspace").hidden = visible; $("new").hidden = visible;
}
async function start() {
  config = await api("/api/config");
  $("receiverLabel").hidden = !config.firebase;
  bind("testDesk", async () => {
    $("testDesk").disabled = true;
    $("testResult").hidden = false; $("testSteps").replaceChildren();
    $("testTitle").textContent = "Checking the release flow…";
    try {
      const result = await api("/api/self-test", {});
      $("testTitle").textContent = result.passed ? "Release checks passed" : "Release check failed";
      $("testSteps").replaceChildren(...result.steps.map(step => {
        const line = document.createElement("li");
        line.textContent = (step.passed ? "Pass · " : "Fail · ") + step.label;
        return line;
      }));
    } catch (err) { $("testTitle").textContent = "Test unavailable"; notice(err.message); }
    finally { $("testDesk").disabled = false; }
  });
  bind("closeTest", () => { $("testResult").hidden = true; });
  $("connection").textContent = config.live ? config.provider + " configured · " + config.model : "Gemini setup required";
  $("policy").textContent = config.auto ? "Aligned packets release automatically" : "Reviewer approval required";
  for (const name of [...Object.keys(config.examples),"Custom"]) $("example").add(new Option(name,name));
  $("example").onchange = selectExample;
  for (const field of ["source","handoff"]) {
    $(field+"File").onchange = () => importConversation(field).catch(e => notice(e.message));
    $(field).oninput = () => { $("example").value = "Custom"; $(field+"File").value = ""; };
  }
  $("filter").onchange = drawQueue; bind("new", () => compose()); bind("revise", () => compose(selected));
  $("compose").onsubmit = async event => {
    event.preventDefault();
    const sequence = ++revision;
    const data = {reference:$("reference").value, source:$("source").value, handoff:$("handoff").value};
    if (editing) data.revises = editing.id;
    if ($("receiverUid").value.trim()) data.receiver_uid = $("receiverUid").value.trim();
    const button = $("submit"); button.disabled = true; button.textContent = "Checking…";
    try {
      const result = await api("/api/reviews", data);
      if (revision === sequence) {notice(""); show(result);} await refresh();
    } catch(e) { notice(e.message); }
    finally {button.disabled = false; button.textContent = "Review handoff →";}
  };
  for (const button of document.querySelectorAll("[data-action]")) {
    button.onclick = async () => {
      const id = selected.id; button.disabled = true;
      try {
        const r = await api(packetPath(id)+"/decision",{decision:button.dataset.action},{"X-Review-Token":$("token").value});
        if (selected?.id === id) { notice(""); show(r); } await refresh();
      } catch(e) { notice(e.message); } finally {button.disabled = false;}
    };
  }
  bind("run", async () => {
    const id = selected.id, result = await api(packetPath(id)+"/simulate");
    if (selected?.id === id) $("simulation").textContent = "2 mock attempts · " + result.charges + " simulated charge" + (result.charges === 1 ? "" : "s");
  });
  compose();
  if (config.firebase) {
    loginView(true);
    $("login").onsubmit = async event => {
      event.preventDefault();
      try {
        const password = $("password").value; $("password").value = "";
        const resp = await fetch("https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=" + encodeURIComponent(config.firebase_web_key),
          {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({email:$("email").value,password,returnSecureToken:true})});
        if (!resp.ok) throw Error("Sign-in failed. Check your Firebase credentials.");
        idToken = (await resp.json()).idToken;
        await refresh(); loginView(false); notice("");
      } catch(e) { idToken = ""; notice(e.message); }
    };
  } else {await refresh();}
  setInterval(() => {if (!document.hidden && (!config.firebase || idToken)) refresh().catch(e=>notice(e.message));},4000);
}
start().catch(e=>notice(e.message));
