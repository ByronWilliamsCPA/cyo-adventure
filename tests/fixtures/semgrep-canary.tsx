// Canary fixture for .semgrep/frontend-security.yml.
//
// This file is deliberately vulnerable. It is never imported, built, bundled or
// shipped: it lives outside frontend/ so tsc, ESLint, Prettier and Vite never
// see it, and it exists only so CI can prove the Semgrep scan still fires.
//
// Why it exists at all: the Semgrep registry packs are close to blind on this
// codebase. Measured 2026-08-24 against eight planted defects with p/react,
// p/typescript, p/javascript, p/xss, p/security-audit and p/owasp-top-ten all
// enabled: 1 of 8 caught. Their React taint sources match `function C({ x })`
// and `function C(x)` but neither `function C({ x }: Props)` nor
// `const C = ({ x }: Props) => ...`, which are the only two shapes this
// codebase uses. A scan can therefore cover every file and still find nothing.
//
// The contract: every site below carries a `// semgrep-expect: <rule-id>`
// marker, and CI compares the NUMBER of markers per rule against the NUMBER of
// findings per rule. There is one site per `pattern-either` alternative, not
// one per rule. Both refinements were forced by measurement rather than
// guessed at:
//
//   - An id-only assertion stayed green after an alternative was broken,
//     because a sibling alternative still matched. Hence counts.
//   - A count-based assertion ALSO stayed green, because the two sites that
//     existed happened to exercise the same alternative. Hence one site per
//     alternative.
//
// Adding a rule or an alternative means adding a site here, or CI fails; that
// is now asserted structurally (alternatives are counted out of the rule file
// and compared against markers) rather than left to the author to remember.
// A rule-count floor covers the last hole: deleting a rule together with its
// sites and markers satisfied every count comparison, because nothing expected
// and nothing found agree.
//
// Do not "fix" the code below. Deleting a marker on its own turns CI red, which
// is the intended behaviour; deleting a marker AND its site together is the
// move that used to pass silently, and is what the floors above now catch.

type Props = { html: string; url: string }

declare function createCanaryClient(key: string): unknown

/* ---- cyo-react-dangerously-set-inner-html ---- */

// Self-closing element, TS-annotated destructured props (registry: MISS).
// semgrep-expect: cyo-react-dangerously-set-inner-html
export function CanaryA({ html }: Props) {
  return <div dangerouslySetInnerHTML={{ __html: html }} />
}

// Self-closing element, arrow component (registry: MISS).
// semgrep-expect: cyo-react-dangerously-set-inner-html
export const CanaryB = ({ html }: Props) => (
  <div dangerouslySetInnerHTML={{ __html: html }} />
)

// Element with children rather than self-closing.
// semgrep-expect: cyo-react-dangerously-set-inner-html
export const CanaryC = ({ html }: Props) => (
  <section dangerouslySetInnerHTML={{ __html: html }}>{null}</section>
)

// Props object form, as passed to React.createElement.
// semgrep-expect: cyo-react-dangerously-set-inner-html
export const canaryProps = ({ html }: Props) => ({
  dangerouslySetInnerHTML: { __html: html },
})

/* ---- cyo-dynamic-code-execution ---- */

// semgrep-expect: cyo-dynamic-code-execution
export const canaryEval = (src: string): unknown => eval(src)

// semgrep-expect: cyo-dynamic-code-execution
export const canaryFnCtor = (src: string): unknown => new Function(src)

// The Function constructor is callable with and without `new`; those parse as
// different nodes, so each needs its own site.
// semgrep-expect: cyo-dynamic-code-execution
export const canaryBareFnCtor = (src: string): unknown => Function(src)

// semgrep-expect: cyo-dynamic-code-execution
export const canaryWindowEval = (src: string): unknown => window.eval(src)

// semgrep-expect: cyo-dynamic-code-execution
export const canaryWindowFnCtor = (src: string): unknown => window.Function(src)

// semgrep-expect: cyo-dynamic-code-execution
export const canaryTimeoutString = (): number => setTimeout('doThing()', 10)

// semgrep-expect: cyo-dynamic-code-execution
export const canaryIntervalString = (): number => setInterval('doThing()', 10)

/* ---- cyo-dom-html-sink ---- */

// semgrep-expect: cyo-dom-html-sink
export const canaryInner = (el: HTMLElement, s: string): void => {
  el.innerHTML = s
}

// semgrep-expect: cyo-dom-html-sink
export const canaryOuter = (el: HTMLElement, s: string): void => {
  el.outerHTML = s
}

// semgrep-expect: cyo-dom-html-sink
export const canaryAdjacent = (el: HTMLElement, s: string): void =>
  el.insertAdjacentHTML('beforeend', s)

// semgrep-expect: cyo-dom-html-sink
export const canaryWrite = (s: string): void => document.write(s)

// semgrep-expect: cyo-dom-html-sink
export const canaryWriteln = (s: string): void => document.writeln(s)

/* ---- cyo-open-redirect ---- */

// semgrep-expect: cyo-open-redirect
export const canaryHrefQualified = ({ url }: Props): void => {
  window.location.href = url
}

// semgrep-expect: cyo-open-redirect
export const canaryHrefBare = ({ url }: Props): void => {
  location.href = url
}

// semgrep-expect: cyo-open-redirect
export const canaryAssign = ({ url }: Props): void => window.location.assign(url)

// semgrep-expect: cyo-open-redirect
export const canaryReplace = ({ url }: Props): void => window.location.replace(url)

/* ---- cyo-postmessage-wildcard-origin ---- */

// semgrep-expect: cyo-postmessage-wildcard-origin
export const canaryPost = (frame: Window, msg: string): void =>
  frame.postMessage(msg, '*')

/* ---- cyo-hardcoded-provider-credential ---- */
/* None of these are real keys: each is a fixed filler run with zero entropy,
   long enough only to satisfy the rule's length floor. */

// semgrep-expect: cyo-hardcoded-provider-credential
const CANARY_ANTHROPIC = 'sk-ant-api03-AAAAAAAAAAAAAAAAAAAAAAAA'  // pragma: allowlist secret
// semgrep-expect: cyo-hardcoded-provider-credential
const CANARY_OPENAI = 'sk-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'  // pragma: allowlist secret
// semgrep-expect: cyo-hardcoded-provider-credential
const CANARY_GITHUB = 'ghp_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'  // pragma: allowlist secret
// semgrep-expect: cyo-hardcoded-provider-credential
const CANARY_GITHUB_PAT = 'github_pat_AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'  // pragma: allowlist secret
// semgrep-expect: cyo-hardcoded-provider-credential
const CANARY_AWS = 'AKIAAAAAAAAAAAAAAAAA' // pragma: allowlist secret
// semgrep-expect: cyo-hardcoded-provider-credential
const CANARY_JWT =  // pragma: allowlist secret
  'eyJAAAAAAAAAAAAAAAAAAAA.AAAAAAAAAAAAAAAAAAAAAA.AAAAAAAAAAAAAAAAAAAAAA' // pragma: allowlist secret

// The shapes an SDK credential actually takes: a config-object property and a
// positional call argument. Neither is an assignment, and the rule matched only
// assignments until PR #754.
// semgrep-expect: cyo-hardcoded-provider-credential
export const canaryClientConfig = { apiKey: 'sk-ant-BBBBBBBBBBBBBBBBBBBB' } // pragma: allowlist secret
// semgrep-expect: cyo-hardcoded-provider-credential
export const canaryClientCall = createCanaryClient('sk-ant-CCCCCCCCCCCCCCCCCCCC') // pragma: allowlist secret

export {
  CANARY_ANTHROPIC,
  CANARY_OPENAI,
  CANARY_GITHUB,
  CANARY_GITHUB_PAT,
  CANARY_AWS,
  CANARY_JWT,
}

/* ---- negative sites: these must NOT fire ----
   These carry no `semgrep-expect` marker on purpose. The CI check compares
   finding counts per rule against marker counts, so if a rule's exclusions
   ever break and one of these starts matching, the count goes over and the
   check fails. The negative cases are policed by the same assertion as the
   positive ones, with no extra machinery. */

export const SafeLiteral = () => <div dangerouslySetInnerHTML={{ __html: '<b>ok</b>' }} />

export const SafeLiteralChildren = () => (
  <section dangerouslySetInnerHTML={{ __html: '<b>ok</b>' }}>{null}</section>
)

export const safeProps = () => ({ dangerouslySetInnerHTML: { __html: '<b>ok</b>' } })

export const safeClear = (el: HTMLElement): void => {
  el.innerHTML = ''
}

export const safeRedirect = (): void => {
  window.location.href = '/guardian/login'
}

// One safe site per exclusion clause, not one per rule. Four of the eight
// `pattern-not` clauses could be deleted with this fixture still green until
// these were added; measured by deleting each clause in turn and re-running the
// canary check. An exclusion with no negative site can rot undetected, which is
// the same silent-drift failure the positive sites exist to prevent, running in
// the opposite direction.
export const safeClearOuter = (el: HTMLElement): void => {
  el.outerHTML = ''
}

export const safeBareRedirect = (): void => {
  location.href = '/guardian/login'
}

export const safeAssign = (): void => {
  window.location.assign('/guardian/login')
}

export const safeReplace = (): void => {
  window.location.replace('/guardian/login')
}

export const safePost = (frame: Window, msg: string): void =>
  frame.postMessage(msg, 'https://cyo.example.com')

const SAFE_NOT_A_KEY = 'this-is-just-a-plain-configuration-string-value'
export { SAFE_NOT_A_KEY }
