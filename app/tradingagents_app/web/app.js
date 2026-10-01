'use strict';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const view = document.getElementById('view');
// Present inside the Android app, which exposes a few native actions.
const android = window.AndroidBridge || null;

function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value == null || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key.startsWith('on')) el.addEventListener(key.slice(2), value);
    else if (key in el) el[key] = value;
    else el.setAttribute(key, value === true ? '' : value);
  }
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    el.append(child.nodeType ? child : document.createTextNode(String(child)));
  }
  return el;
}

async function api(path, body) {
  const response = await fetch(path, body === undefined ? {} : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`);
  return data;
}

DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank');
    node.setAttribute('rel', 'noopener noreferrer');
  }
});

// Reports are model output built from fetched web data: render as markdown,
// then strip anything that is not plain formatting.
function markdown(text) {
  const el = h('div', { class: 'markdown' });
  el.innerHTML = DOMPurify.sanitize(marked.parse(text || '', { gfm: true, breaks: false }), {
    FORBID_TAGS: ['style', 'form', 'input', 'button', 'img', 'video', 'audio', 'iframe'],
  });
  return el;
}

const pad = (n) => String(n).padStart(2, '0');

function formatElapsed(ms) {
  const total = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(total / 3600);
  const rest = `${pad(Math.floor((total % 3600) / 60))}:${pad(total % 60)}`;
  return hours ? `${hours}:${rest}` : rest;
}

const formatCount = (n) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n || 0));

function formatDateTime(ms) {
  return new Date(ms).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
}

function ratingBadge(rating) {
  const label = rating === 'REVIEW' ? 'Needs review' : rating || '—';
  return h('span', { class: `rating rating-${String(rating || 'none').toLowerCase()}` }, label);
}

function toast(message, kind = 'error') {
  const el = h('div', { class: `toast ${kind}`, role: 'alert' }, message);
  document.body.append(el);
  setTimeout(() => el.remove(), 6000);
}

// ---------------------------------------------------------------------------
// Report viewer: the sections of a run, one shown at a time
// ---------------------------------------------------------------------------

const SECTION_GROUPS = [
  ['Analysts', [['market_report', 'Market'], ['sentiment_report', 'Sentiment'],
                ['news_report', 'News'], ['fundamentals_report', 'Fundamentals']]],
  ['Research', [['bull_history', 'Bull'], ['bear_history', 'Bear'], ['investment_plan', 'Research manager']]],
  ['Trading', [['trader_investment_plan', 'Trader']]],
  ['Risk', [['aggressive_history', 'Aggressive'], ['conservative_history', 'Conservative'],
            ['neutral_history', 'Neutral']]],
  ['Decision', [['final_trade_decision', 'Portfolio manager']]],
];
const SPEAKER_PREFIX = /^((?:Bull|Bear|Aggressive|Conservative|Neutral) Analyst):[ \t]*/gm;
const SECTION_TITLES = Object.fromEntries(SECTION_GROUPS.flatMap(([group, sections]) =>
  sections.map(([key, label]) => [key, `${group} · ${label}`])));

class ReportViewer {
  constructor(emptyText) {
    this.reports = {};
    this.selected = null;
    // Until the reader picks a section, show whichever was written last.
    this.follow = true;
    this.emptyText = emptyText;
    this.tabs = h('div', { class: 'tabs', role: 'tablist' });
    this.body = h('div', { class: 'report-body' });
    this.el = h('div', { class: 'viewer' }, this.tabs, this.body);
    this.render();
  }

  set(section, text) {
    this.reports[section] = text;
    if (this.follow || !this.selected) this.selected = section;
    this.render(this.selected === section);
  }

  select(section, byReader = false) {
    if (!(section in this.reports)) return;
    if (byReader) this.follow = false;
    this.selected = section;
    this.render(true);
    this.body.scrollTop = 0;
  }

  text() {
    return SECTION_GROUPS.flatMap(([, sections]) => sections)
      .filter(([key]) => this.reports[key])
      .map(([key]) => `# ${SECTION_TITLES[key]}\n\n${this.reports[key]}`)
      .join('\n\n---\n\n');
  }

  render(body = true) {
    this.tabs.replaceChildren(...SECTION_GROUPS.map(([group, sections]) => {
      const available = sections.filter(([key]) => this.reports[key]);
      return available.length && h('div', { class: 'tab-group' },
        h('span', { class: 'tab-group-name' }, group),
        available.map(([key, label]) => h('button', {
          class: key === this.selected ? 'tab active' : 'tab',
          role: 'tab',
          type: 'button',
          onclick: () => this.select(key, true),
        }, label)));
    }).filter(Boolean));
    if (!body) return;
    const scroll = this.body.scrollTop;
    if (this.selected) {
      let text = this.reports[this.selected];
      // A debate history is its speaker's turns, each opened "Bull Analyst: ...".
      // Give the label a line of its own so the turn's markdown renders.
      if (this.selected.endsWith('_history')) text = text.replace(SPEAKER_PREFIX, '\n\n#### $1\n\n');
      this.body.replaceChildren(
        h('h2', { class: 'report-title' }, SECTION_TITLES[this.selected]),
        markdown(text));
      this.body.scrollTop = scroll;
    } else {
      this.body.replaceChildren(h('p', { class: 'empty' }, this.emptyText));
    }
  }
}

// On Android the report goes to the share sheet; on a PC, to the clipboard.
function exportButton(title, getText) {
  if (android) {
    return h('button', { class: 'ghost small', type: 'button',
      onclick: () => android.share(title, getText()) }, 'Share report');
  }
  const button = h('button', { class: 'ghost small', type: 'button' }, 'Copy full report');
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(getText());
      button.textContent = 'Copied';
    } catch {
      button.textContent = 'Copy failed';
    }
    setTimeout(() => { button.textContent = 'Copy full report'; }, 2000);
  });
  return button;
}

// ---------------------------------------------------------------------------
// App state and the live run
// ---------------------------------------------------------------------------

const state = {
  boot: null,
  // Server clock minus this device's, so elapsed time is right on a phone too.
  clockOffset: 0,
  live: null,       // the current run as seen so far
  source: null,     // its EventSource
};

function newLive(run) {
  return {
    run,
    agents: {},
    feed: [],
    stats: { llm_calls: 0, tool_calls: 0, tokens_in: 0, tokens_out: 0 },
    result: null,
    error: null,
    viewer: new ReportViewer('Reports appear here as each agent finishes.'),
    lastSeq: 0,
  };
}

function followRun(run) {
  if (state.source) state.source.close();
  state.source = null;
  state.live = run ? newLive(run) : null;
  updateNav();
  if (!run) return;

  const live = state.live;
  const source = new EventSource(`/api/run/events?id=${encodeURIComponent(run.id)}`);
  state.source = source;
  source.onmessage = (message) => {
    const event = JSON.parse(message.data);
    if (event.seq <= live.lastSeq) return;
    live.lastSeq = event.seq;
    applyEvent(live, event);
  };
  source.onerror = () => {
    // The browser retries by itself while the engine is reachable. A closed
    // source means the engine refused: it restarted and the run is gone.
    if (source.readyState === EventSource.CLOSED && live.run.status === 'running') {
      live.run.status = 'error';
      live.error = 'Lost the connection to the engine.';
      runView.refresh();
      updateNav();
    }
  };
}

function applyEvent(live, event) {
  switch (event.type) {
    case 'status':
      live.agents[event.agent] = event.status;
      runView.agent(event.agent);
      break;
    case 'report':
      live.viewer.set(event.section, event.text);
      break;
    case 'message':
      pushFeed(live, { time: event.time, kind: event.kind, text: event.text });
      break;
    case 'tool':
      pushFeed(live, { time: event.time, kind: 'Tool', text: `${event.name}  ${event.args}` });
      break;
    case 'stats':
      live.stats = event;
      runView.stats();
      break;
    case 'done':
      live.run.status = 'completed';
      live.result = event;
      live.viewer.follow = false;
      live.viewer.select('final_trade_decision');
      finishLive(live);
      break;
    case 'error':
      live.run.status = 'error';
      live.error = event.message;
      finishLive(live);
      break;
    case 'cancelled':
      live.run.status = 'cancelled';
      finishLive(live);
      break;
  }
}

function finishLive(live) {
  // A run that ended before this page opened already says when.
  if (!live.run.finished_at) live.run.finished_at = Date.now() + state.clockOffset;
  if (state.source) state.source.close();
  state.source = null;
  runView.refresh();
  updateNav();
}

function pushFeed(live, entry) {
  live.feed.push(entry);
  if (live.feed.length > 500) live.feed.shift();
  runView.feed(entry);
}

function updateNav() {
  const running = state.live && state.live.run.status === 'running';
  document.getElementById('nav-live').hidden = !running;
  // The Android app keeps the engine alive in the background while a run lasts.
  if (android) android.setRunning(Boolean(running));
}

// ---------------------------------------------------------------------------
// View: live run
// ---------------------------------------------------------------------------

const STATUS_LABELS = { pending: 'Waiting', in_progress: 'Working', completed: 'Done', error: 'Failed' };
const RUN_STATUS = { running: 'Running', completed: 'Completed', error: 'Failed', cancelled: 'Stopped' };

const runView = {
  mounted: false,
  nodes: {},
  timer: null,

  mount() {
    const live = state.live;
    this.unmount();
    if (!live) {
      view.replaceChildren(h('div', { class: 'card center-card' },
        h('h1', {}, 'No analysis yet'),
        h('p', { class: 'muted' }, 'Start one and watch the agents work here.'),
        h('a', { class: 'button primary', href: '#/new' }, 'New analysis')));
      return;
    }
    const { run } = live;
    const request = run.request;
    const n = this.nodes = {};

    n.status = h('span', { class: 'pill' });
    n.elapsed = h('span', { class: 'chip', title: 'Elapsed time' });
    n.llm = h('span', { class: 'chip' });
    n.tools = h('span', { class: 'chip' });
    n.tokens = h('span', { class: 'chip', title: 'Tokens sent / received' });
    n.stop = h('button', { class: 'danger small', type: 'button', onclick: () => this.stop() }, 'Stop');
    n.banner = h('div', { class: 'banner-slot' });

    n.agents = {};
    n.progress = h('div', { class: 'teams' }, run.teams.filter((team) => team.agents.length).map((team) =>
      h('div', { class: 'team' },
        h('h3', {}, team.name),
        team.agents.map((agent) => {
          const row = h('div', { class: 'agent' }, h('span', { class: 'dot' }),
            h('span', { class: 'agent-name' }, agent), h('span', { class: 'agent-status' }));
          n.agents[agent] = row;
          return row;
        }))));

    n.feed = h('div', { class: 'feed' });
    n.copy = exportButton(`${request.ticker} analysis, ${request.date}`, () => live.viewer.text());

    view.replaceChildren(h('section', { class: 'run' },
      h('div', { class: 'run-head' },
        h('div', {},
          h('h1', {}, request.ticker, request.asset_type === 'crypto' && h('span', { class: 'tag' }, 'crypto')),
          h('p', { class: 'muted' },
            `As of ${request.date} · ${providerName(request.provider)} · ${request.deep_model} / ${request.quick_model}`)),
        h('div', { class: 'run-meta' }, n.status, n.elapsed, n.llm, n.tools, n.tokens, n.stop)),
      n.banner,
      h('div', { class: 'run-grid' },
        h('details', { class: 'panel progress', open: window.innerWidth > 760 },
          h('summary', {}, 'Agents'), n.progress),
        h('div', { class: 'panel reports' },
          h('div', { class: 'panel-head' }, h('h2', {}, 'Reports'), n.copy), live.viewer.el),
        h('details', { class: 'panel activity', open: window.innerWidth > 760 },
          h('summary', {}, 'Activity'), n.feed))));

    this.mounted = true;
    Object.keys(n.agents).forEach((agent) => this.agent(agent));
    n.feed.append(...live.feed.map(feedRow));
    n.feed.scrollTop = n.feed.scrollHeight;
    this.stats();
    this.refresh();
    this.timer = setInterval(() => this.tick(), 1000);
  },

  unmount() {
    this.mounted = false;
    clearInterval(this.timer);
  },

  agent(name) {
    if (!this.mounted || !this.nodes.agents[name]) return;
    const status = state.live.agents[name] || 'pending';
    const row = this.nodes.agents[name];
    row.className = `agent ${status}`;
    row.lastChild.textContent = STATUS_LABELS[status] || status;
  },

  feed(entry) {
    if (!this.mounted) return;
    const feed = this.nodes.feed;
    const atBottom = feed.scrollHeight - feed.scrollTop - feed.clientHeight < 60;
    feed.append(feedRow(entry));
    while (feed.childElementCount > 500) feed.firstElementChild.remove();
    if (atBottom) feed.scrollTop = feed.scrollHeight;
  },

  stats() {
    if (!this.mounted) return;
    const { stats } = state.live;
    this.nodes.llm.textContent = `${stats.llm_calls} LLM calls`;
    this.nodes.tools.textContent = `${stats.tool_calls} tool calls`;
    this.nodes.tokens.textContent = `${formatCount(stats.tokens_in)} in · ${formatCount(stats.tokens_out)} out`;
  },

  tick() {
    if (!this.mounted) return;
    const { run } = state.live;
    const end = run.finished_at || Date.now() + state.clockOffset;
    this.nodes.elapsed.textContent = formatElapsed(end - run.started_at);
  },

  // Everything that depends on whether the run is still going.
  refresh() {
    if (!this.mounted) return;
    const live = state.live;
    const { status } = live.run;
    const n = this.nodes;
    n.status.className = `pill ${status}`;
    n.status.textContent = RUN_STATUS[status] || status;
    n.stop.hidden = status !== 'running';
    n.copy.hidden = status === 'running';
    this.tick();

    if (status === 'completed' && live.result) {
      const { rating, review, report_path: path } = live.result;
      n.banner.replaceChildren(h('div', { class: 'banner done' },
        h('div', {}, h('span', { class: 'banner-label' }, 'Final decision'), ratingBadge(rating)),
        h('div', { class: 'banner-text' },
          review && h('p', {}, 'No rating could be read from the final decision. Read the Portfolio manager’s text and judge it yourself, or run it again.'),
          // On Android the folder is inside the app's private storage; History shows the run instead.
          path && !android && h('p', { class: 'muted' }, `Report saved to ${path}`)),
        h('a', { class: 'button', href: '#/new' }, 'New analysis')));
    } else if (status === 'error') {
      n.banner.replaceChildren(h('div', { class: 'banner failed' },
        h('div', { class: 'banner-text' }, h('strong', {}, 'The analysis stopped with an error'),
          h('p', {}, live.error || 'Unknown error.')),
        h('a', { class: 'button', href: '#/new' }, 'Back to the form')));
    } else if (status === 'cancelled') {
      n.banner.replaceChildren(h('div', { class: 'banner' },
        h('div', { class: 'banner-text' }, h('strong', {}, 'Stopped'),
          h('p', { class: 'muted' }, 'The reports written so far are below.')),
        h('a', { class: 'button', href: '#/new' }, 'New analysis')));
    } else {
      n.banner.replaceChildren();
    }
  },

  async stop() {
    this.nodes.stop.disabled = true;
    this.nodes.stop.textContent = 'Stopping…';
    try {
      await api('/api/run/cancel', {});
    } catch (error) {
      toast(error.message);
    }
  },
};

function feedRow(entry) {
  const text = h('span', { class: 'feed-text' }, entry.text);
  const row = h('div', { class: `feed-row kind-${entry.kind.toLowerCase()}` },
    h('span', { class: 'feed-time' }, entry.time), h('span', { class: 'feed-kind' }, entry.kind), text);
  row.addEventListener('click', () => row.classList.toggle('open'));
  return row;
}

function providerName(key) {
  const provider = state.boot.providers.find((p) => p.key === key);
  return provider ? provider.name : key;
}

// ---------------------------------------------------------------------------
// View: new analysis
// ---------------------------------------------------------------------------

const CRYPTO_SUFFIXES = ['-USD', '-USDT', '-USDC', '-BTC', '-ETH'];

function field(label, control, hint) {
  return h('label', { class: 'field' }, h('span', { class: 'field-label' }, label), control,
    hint && h('span', { class: 'hint' }, hint));
}

// A model picker: the provider's list, or free text when "Custom" is chosen.
function modelPicker(label) {
  const select = h('select', {});
  const custom = h('input', { type: 'text', placeholder: 'Model ID', spellcheck: false, hidden: true });
  select.addEventListener('change', () => { custom.hidden = select.value !== 'custom'; });
  return {
    el: field(label, h('div', { class: 'stack' }, select, custom)),
    fill(options, preferred) {
      select.replaceChildren(...options.map((o) => h('option', { value: o.id }, o.label)));
      const known = options.some((o) => o.id === preferred && o.id !== 'custom');
      if (known) select.value = preferred;
      else if (preferred) { select.value = 'custom'; custom.value = preferred; }
      else custom.value = '';
      custom.hidden = select.value !== 'custom';
    },
    value: () => (select.value === 'custom' ? custom.value.trim() : select.value),
  };
}

function mountNew() {
  const { boot } = state;
  const prefs = boot.prefs || {};
  const running = state.live && state.live.run.status === 'running';

  const ticker = h('input', { type: 'text', placeholder: 'NVDA', value: prefs.ticker || '', maxLength: 32,
    spellcheck: false, autocapitalize: 'characters', autocomplete: 'off', required: true });
  const date = h('input', { type: 'date', value: boot.today, max: boot.today, required: true });

  const analystBoxes = boot.analysts.map((analyst) => {
    const box = h('input', { type: 'checkbox', value: analyst.key,
      checked: prefs.analysts ? prefs.analysts.includes(analyst.key) : true });
    return { key: analyst.key, box, el: h('label', { class: 'choice' }, box,
      h('span', {}, h('strong', {}, analyst.name), h('small', {}, analyst.hint))) };
  });
  const syncAssetType = () => {
    const symbol = ticker.value.trim().toUpperCase();
    const crypto = CRYPTO_SUFFIXES.some((suffix) => symbol.endsWith(suffix));
    const fundamentals = analystBoxes.find((a) => a.key === 'fundamentals');
    fundamentals.box.disabled = crypto;
    fundamentals.el.classList.toggle('disabled', crypto);
    fundamentals.el.title = crypto ? 'Not available for crypto' : '';
  };
  ticker.addEventListener('input', syncAssetType);

  const depths = boot.depths.map((depth) => {
    const radio = h('input', { type: 'radio', name: 'depth', value: String(depth.value),
      checked: (prefs.depth || 1) === depth.value });
    return h('label', { class: 'choice' }, radio,
      h('span', {}, h('strong', {}, depth.name), h('small', {}, depth.hint)));
  });

  const provider = h('select', {}, boot.providers.map((p) => h('option', { value: p.key }, p.name)));
  if (boot.providers.some((p) => p.key === prefs.provider)) provider.value = prefs.provider;
  const keyNote = h('div', { class: 'key-note' });
  const url = h('input', { type: 'url', spellcheck: false });
  const urlField = field('Server URL', url);
  const quick = modelPicker('Quick-thinking model');
  const deep = modelPicker('Deep-thinking model');
  const effort = h('select', {});
  const effortField = field('Effort', effort);

  const language = h('select', {},
    boot.languages.map((name) => h('option', { value: name }, name)), h('option', { value: 'custom' }, 'Other…'));
  const customLanguage = h('input', { type: 'text', placeholder: 'Language name', hidden: true });
  if (prefs.language && !boot.languages.includes(prefs.language)) {
    language.value = 'custom';
    customLanguage.value = prefs.language;
    customLanguage.hidden = false;
  } else if (prefs.language) {
    language.value = prefs.language;
  }
  language.addEventListener('change', () => { customLanguage.hidden = language.value !== 'custom'; });

  const checkpoint = h('input', { type: 'checkbox', checked: Boolean(prefs.checkpoint) });

  const syncProvider = async () => {
    const p = boot.providers.find((item) => item.key === provider.value);
    const remembered = prefs.provider === p.key ? prefs : {};

    if (p.key_status === 'missing' && !p.key_optional) {
      keyNote.replaceChildren(h('span', { class: 'warn' }, `No API key saved for ${p.name}. `),
        h('a', { href: '#/settings' }, 'Add it in Settings'));
    } else {
      keyNote.replaceChildren();
    }

    urlField.hidden = !p.url_editable;
    url.value = remembered.backend_url || p.default_url || '';
    url.placeholder = p.default_url || 'http://localhost:1234/v1';

    effortField.hidden = !p.effort;
    if (p.effort) {
      effortField.querySelector('.field-label').textContent = p.effort.label;
      effort.replaceChildren(h('option', { value: '' }, 'Provider default'),
        ...p.effort.options.map((o) => h('option', { value: o.value }, o.label)));
      effort.value = remembered.effort || '';
    }

    quick.fill(p.models.quick, remembered.quick_model);
    deep.fill(p.models.deep, remembered.deep_model);
    if (p.dynamic_models) {
      try {
        const { models } = await api('/api/openrouter-models');
        if (provider.value !== p.key) return;
        const options = [...models, { label: 'Custom model ID', id: 'custom' }];
        quick.fill(options, remembered.quick_model);
        deep.fill(options, remembered.deep_model);
      } catch (error) {
        toast(error.message);
      }
    }
  };
  provider.addEventListener('change', syncProvider);

  const error = h('p', { class: 'form-error', role: 'alert', hidden: true });
  const submit = h('button', { class: 'primary large', type: 'submit', disabled: running }, 'Start analysis');

  const form = h('form', { class: 'new-form' },
    h('div', { class: 'card' },
      h('h2', {}, 'What to analyze'),
      h('div', { class: 'row' },
        field('Ticker', ticker, 'Stocks, ETFs and indices as on Yahoo Finance (NVDA, 0700.HK, ^GSPC); crypto as BTC-USD.'),
        field('Analysis date', date, 'Data is used as of this date.'))),
    h('div', { class: 'card' },
      h('h2', {}, 'Analyst team'),
      h('div', { class: 'choices' }, analystBoxes.map((a) => a.el))),
    h('div', { class: 'card' },
      h('h2', {}, 'Research depth'),
      h('div', { class: 'choices three' }, depths),
      h('p', { class: 'hint' }, 'Deeper research runs more debate rounds: better-argued decisions, more time and tokens.')),
    h('div', { class: 'card' },
      h('h2', {}, 'Models'),
      field('LLM provider', provider), keyNote, urlField,
      h('div', { class: 'row' }, quick.el, deep.el),
      h('div', { class: 'row' }, effortField,
        field('Report language', h('div', { class: 'stack' }, language, customLanguage))),
      h('label', { class: 'inline-check' }, checkpoint,
        'Save progress so a run that stops can be resumed (checkpoint)')),
    error,
    h('div', { class: 'form-actions' },
      submit,
      running && h('a', { class: 'button', href: '#/run' }, 'An analysis is running — view it')),
    h('p', { class: 'disclaimer' },
      'TradingAgents is a research framework. Its output depends on the models and data used and is not financial, investment or trading advice.'));

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    error.hidden = true;
    submit.disabled = true;
    const payload = {
      ticker: ticker.value.trim(),
      date: date.value,
      analysts: analystBoxes.filter((a) => a.box.checked && !a.box.disabled).map((a) => a.key),
      depth: Number(form.querySelector('input[name=depth]:checked').value),
      provider: provider.value,
      quick_model: quick.value(),
      deep_model: deep.value(),
      backend_url: url.value.trim(),
      effort: effort.value || null,
      language: language.value === 'custom' ? customLanguage.value.trim() : language.value,
      checkpoint: checkpoint.checked,
    };
    try {
      const { run } = await api('/api/run', payload);
      state.boot.prefs = { ...payload };
      followRun(run);
      location.hash = '#/run';
    } catch (failure) {
      error.textContent = failure.message;
      error.hidden = false;
      submit.disabled = false;
    }
  });

  view.replaceChildren(h('section', { class: 'narrow' },
    h('h1', {}, 'New analysis'),
    h('p', { class: 'muted lead' },
      'A team of AI agents — analysts, bull and bear researchers, a trader, risk managers and a portfolio manager — studies one instrument and reaches a rating.'),
    form));
  syncAssetType();
  syncProvider();
}

// ---------------------------------------------------------------------------
// View: history
// ---------------------------------------------------------------------------

async function mountHistory(ticker, date) {
  if (ticker && date) return mountHistoryRun(ticker, date);
  view.replaceChildren(h('p', { class: 'loading' }, 'Loading…'));
  const { runs } = await api('/api/history');
  if (!runs.length) {
    view.replaceChildren(h('div', { class: 'card center-card' },
      h('h1', {}, 'No past analyses'),
      h('p', { class: 'muted' }, 'Finished analyses are kept here, including ones run from the command line.'),
      h('a', { class: 'button primary', href: '#/new' }, 'New analysis')));
    return;
  }
  view.replaceChildren(h('section', {},
    h('h1', {}, 'History'),
    h('div', { class: 'card list' }, runs.map((run) =>
      h('a', { class: 'list-row', href: `#/history/${encodeURIComponent(run.ticker)}/${run.date}` },
        h('strong', { class: 'list-ticker' }, run.ticker),
        h('span', {}, run.date),
        ratingBadge(run.rating),
        h('span', { class: 'muted list-models' },
          [run.provider && providerName(run.provider), run.deep_model].filter(Boolean).join(' · ')),
        h('span', { class: 'muted list-saved' }, formatDateTime(run.saved_at)))))));
}

async function mountHistoryRun(ticker, date) {
  view.replaceChildren(h('p', { class: 'loading' }, 'Loading…'));
  const run = await api(`/api/history/run?ticker=${encodeURIComponent(ticker)}&date=${encodeURIComponent(date)}`);
  const viewer = new ReportViewer('This run has no saved reports.');
  viewer.follow = false;
  for (const [section, text] of Object.entries(run.reports)) viewer.set(section, text);
  viewer.select(run.reports.final_trade_decision ? 'final_trade_decision' : Object.keys(run.reports)[0]);
  const s = run.settings;
  view.replaceChildren(h('section', { class: 'run' },
    h('div', { class: 'run-head' },
      h('div', {},
        h('a', { class: 'back', href: '#/history' }, '← History'),
        h('h1', {}, run.ticker, ' ', ratingBadge(run.rating)),
        h('p', { class: 'muted' }, [`As of ${run.date}`, s.llm_provider && providerName(s.llm_provider),
          s.deep_think_llm && `${s.deep_think_llm} / ${s.quick_think_llm}`].filter(Boolean).join(' · '))),
      h('div', { class: 'run-meta' }, exportButton(`${run.ticker} analysis, ${run.date}`, () => viewer.text()))),
    h('div', { class: 'panel reports' }, viewer.el)));
}

// ---------------------------------------------------------------------------
// View: settings
// ---------------------------------------------------------------------------

const KEY_STATUS = {
  saved: ['Saved in this app', 'ok'],
  environment: ['Set in the system environment', 'ok'],
  missing: ['Not set', 'off'],
};

function settingRow(env, label, hint, status, secret) {
  const [statusText, statusClass] = KEY_STATUS[status];
  const row = h('div', { class: 'setting' },
    h('div', { class: 'setting-name' }, h('strong', {}, label), h('small', {}, hint || env)),
    h('span', { class: `badge ${statusClass}` }, statusText));

  const input = h('input', { type: secret ? 'password' : 'text', autocomplete: 'off', spellcheck: false,
    placeholder: status === 'saved' ? 'Replace saved value' : secret ? 'Paste key' : 'Enter value',
    'aria-label': label });
  const save = async (value) => {
    try {
      await api('/api/settings/key', { name: env, value });
      await reloadBoot();
      mountSettings();
    } catch (error) {
      toast(error.message);
    }
  };
  row.append(h('form', { class: 'setting-edit', onsubmit: (event) => {
    event.preventDefault();
    if (input.value.trim()) save(input.value.trim());
  } }, input, h('button', { class: 'small', type: 'submit' }, 'Save'),
    status === 'saved' && h('button', { class: 'ghost small', type: 'button', onclick: () => save('') }, 'Remove')));
  return row;
}

const THEME_LABELS = {
  system: ['System', 'Follows this computer’s light or dark mode'],
  dark: ['Dark', 'Light text on a dark background'],
  light: ['Light', 'Dark text on a light background'],
};

// Use a theme now: in the page, and on Android in the app's own bars around it.
function applyTheme(theme) {
  if (theme === 'system') delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
  if (android) android.setTheme(theme);
}

function appearanceCard() {
  const { boot } = state;
  const choose = async (theme) => {
    try {
      await api('/api/settings/theme', { theme });
      boot.theme = theme;
      applyTheme(theme);
    } catch (error) {
      toast(error.message);
      mountSettings();
    }
  };
  return h('div', { class: 'card' },
    h('h2', {}, 'Appearance'),
    h('div', { class: boot.themes.length > 2 ? 'choices three' : 'choices' }, boot.themes.map((theme) =>
      h('label', { class: 'choice' },
        h('input', { type: 'radio', name: 'theme', checked: theme === boot.theme, onchange: () => choose(theme) }),
        h('span', {}, h('strong', {}, THEME_LABELS[theme][0]), h('small', {}, THEME_LABELS[theme][1]))))));
}

// Where a saved key is kept, said plainly for the platform the app runs on.
const KEY_STORAGE = {
  windows: 'Keys are stored on this PC, encrypted for your Windows account.',
  android: 'Keys are stored in this app’s private storage on this device.',
};

function mountSettings() {
  const { boot } = state;
  // Regional variants share nothing, but one row per distinct key is enough.
  const seen = new Set();
  const providerRows = boot.providers.filter((p) => p.key_env && !seen.has(p.key_env) && seen.add(p.key_env))
    .map((p) => settingRow(p.key_env, p.name, p.key_env, p.key_status, true));

  view.replaceChildren(h('section', { class: 'narrow' },
    h('h1', {}, 'Settings'),
    h('div', { class: 'card' },
      h('h2', {}, 'LLM provider keys'),
      h('p', { class: 'muted' }, 'You need a key for the provider you choose on the form. ', KEY_STORAGE[boot.platform] || ''),
      providerRows),
    h('div', { class: 'card' },
      h('h2', {}, 'Data sources (optional)'),
      h('p', { class: 'muted' }, 'Market data, news and fundamentals work without any of these.'),
      boot.extra_settings.map((s) => settingRow(s.env, s.label, s.hint, s.status, s.secret))),
    appearanceCard(),
    h('div', { class: 'card' },
      h('h2', {}, 'About'),
      h('p', { class: 'muted' },
        `App ${boot.app_version} · TradingAgents framework ${boot.framework_version} by `,
        h('a', { href: 'https://github.com/TauricResearch/TradingAgents' }, 'Tauric Research'), ' (Apache-2.0).'),
      h('p', { class: 'disclaimer' },
        'For research purposes. Not financial, investment or trading advice.'))));
}

// ---------------------------------------------------------------------------
// Routing and startup
// ---------------------------------------------------------------------------

async function reloadBoot() {
  const boot = await api('/api/bootstrap');
  state.boot = boot;
  return boot;
}

async function route() {
  const [name = 'new', ...rest] = location.hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
  runView.unmount();
  document.querySelectorAll('#nav a').forEach((link) =>
    link.classList.toggle('active', link.dataset.route === (name || 'new')));
  window.scrollTo(0, 0);
  try {
    if (name === 'run') runView.mount();
    else if (name === 'history') await mountHistory(rest[0], rest[1]);
    else if (name === 'settings') mountSettings();
    else mountNew();
  } catch (error) {
    view.replaceChildren(h('div', { class: 'card center-card' },
      h('h1', {}, 'Something went wrong'), h('p', { class: 'muted' }, error.message)));
  }
}

async function start() {
  try {
    const before = Date.now();
    const boot = await reloadBoot();
    state.clockOffset = boot.now - (before + Date.now()) / 2;
    applyTheme(boot.theme);
    if (boot.run) followRun(boot.run);
    window.addEventListener('hashchange', route);
    // Setting the hash fires hashchange, which routes.
    if (!location.hash) location.replace(boot.run && boot.run.status === 'running' ? '#/run' : '#/new');
    else route();
  } catch (error) {
    view.replaceChildren(h('div', { class: 'card center-card' },
      h('h1', {}, 'Could not reach the engine'), h('p', { class: 'muted' }, error.message),
      h('button', { class: 'primary', type: 'button', onclick: () => location.reload() }, 'Try again')));
  }
}

start();
