export const meta = {
  name: 'rubric',
  description: 'Build a rubric for one assignment: read a random sample of submissions, write solutions and accepted methods, a 5-member council debates, field-test on fresh submissions, critique, final check',
  whenToUse: 'Run from the rubric skill (.claude/skills/rubric/SKILL.md) after questions.md and the page sample are ready. args: {work, template, sample, fresh}',
  phases: [
    { title: 'Read', detail: '5 readers over the sample + the solutions writer' },
    { title: 'Draft', detail: 'findings, methods page, rubric v1' },
    { title: 'Council', detail: '5 roles + 2 field-test TAs' },
    { title: 'Vote', detail: 'only on the contested points' },
    { title: 'Write', detail: 'chair writes the rubric from the template' },
    { title: 'Critique', detail: 'up to 2 rounds, 3 critics' },
    { title: 'Check', detail: 'points, coverage, answers, privacy' },
  ],
}

// args: { work: folder with questions.md, manifest.json and pages/; template: path to rubric-template.md;
//         sample: [numbers]; fresh: [numbers] }
const W = args.work
const PAGES = `${W}\\pages`
const SAMPLE = args.sample
const FRESH = args.fresh.slice(0, 6)
const PRIVACY = 'Never write student names, ID numbers or emails; refer to submissions only by their 4-digit number.'
const SRC = `Sources in ${W}: questions.md (printed question text verbatim, the lecturer's solutions, and what the course has taught so far).`
const PAGES_HOW = `Page images are in ${PAGES}, named <number>_pNN.jpg (blank pages were already removed). Glob for each number and Read every page.`

// ---------- Read ----------
phase('Read')
const SCAN = { type: 'object', properties: {
  per_part: { type: 'array', items: { type: 'object', properties: {
    part: { type: 'string' }, correct: { type: 'number' }, attempted: { type: 'number' },
    mistakes: { type: 'array', items: { type: 'object', properties: {
      what: { type: 'string', description: 'the mistake, with one concrete example of what was written' },
      submissions: { type: 'array', items: { type: 'string' } } }, required: ['what', 'submissions'] } },
    methods: { type: 'array', items: { type: 'object', properties: {
      method: { type: 'string' }, submissions: { type: 'array', items: { type: 'string' } } }, required: ['method', 'submissions'] } },
  }, required: ['part', 'correct', 'attempted', 'mistakes', 'methods'] } },
  out_of_scope: { type: 'array', items: { type: 'string' }, description: 'method + part + submission' },
  submission_issues: { type: 'array', items: { type: 'string' }, description: 'wrong file, missing questions, illegible, order, answers only, cover pages...' },
}, required: ['per_part', 'out_of_scope', 'submission_issues'] }

const groups = []
for (let i = 0; i < SAMPLE.length; i += 10) groups.push(SAMPLE.slice(i, i + 10))

const scansP = parallel(groups.map((g, i) => () => agent(
  `Survey student submissions to build a rubric. ${SRC} Read questions.md first.\n${PAGES_HOW}\nSubmissions: ${g.join(' ')}\n\nFor every part of every question, record how many attempted it and got it fully right, EVERY distinct mistake (also reasoning errors behind a right answer, notation, missing counterexamples, sign errors, copy errors) with the submission numbers, and every method used. Flag anything beyond what the course has taught. Aggregate only: no per-submission tables. If a page is unreadable, say so instead of guessing. ${PRIVACY}`,
  { label: `read:${i + 1}`, phase: 'Read', model: 'sonnet', schema: SCAN })))

const solutionsP = agent(
  `${SRC}\nWrite ${W}\\Solutions.md: the full solution sheet in Hebrew (Markdown, math in $...$), for every assigned question and part, based on the lecturer's solutions in questions.md. Where the source only says "similarly", write the steps out. Recompute every number and add a one-line check (substitute back) wherever one exists. Box each final answer. Keep it tight: no prose beyond what a TA needs. Return the list of parts as labels like 11א, 12ב (in the order they appear).`,
  { label: 'solutions', phase: 'Read', schema: { type: 'object', properties: { parts: { type: 'array', items: { type: 'string' } } }, required: ['parts'] } })

const [scans, sol] = await Promise.all([scansP, solutionsP])
const PARTS = sol.parts
const scanText = JSON.stringify(scans.filter(Boolean))
log(`Read ${SAMPLE.length} submissions in ${groups.length} groups; ${PARTS.length} parts`)

// ---------- Draft ----------
phase('Draft')
await agent(
  `Merge these reader reports (JSON) into ${W}\\findings.md, in English: per part, % correct, each mistake with count and the submission numbers, each method with count; then out-of-scope methods; then submission-level issues (wrong file, missing, illegible...). Merge duplicates across readers. Compact: tables and lists, no prose. ${PRIVACY}\n\n${scanText}`,
  { label: 'findings', phase: 'Draft', model: 'sonnet' })

const PARTS_SCHEMA = { type: 'object', properties: { parts: { type: 'array', items: { type: 'object', properties: {
  label: { type: 'string', enum: PARTS }, points: { type: 'number' } }, required: ['label', 'points'] } } }, required: ['parts'] }
const v1 = await agent(
  `${SRC} Also read ${W}\\Solutions.md and ${W}\\findings.md.\nWrite two files, in Hebrew:\n1. ${W}\\Solution methods.md: for each question, every correct method within what the course has taught (with how many submissions used it), the reasoning that is NOT acceptable (with real examples from findings), and a final section "מחוץ לחומר – זה לא הפתרון": a table of methods beyond the course so far (how to recognize each, where it might appear), saying that how they are scored is in the rubric.\n2. ${W}\\Rubric v1.md: a first 0-100 rubric: points per part (weight by what each part tests and by where students actually fail), and for each part a short table of the main cases seen in findings → points. List at the end the open decisions for the lecturer, marked ⚠.\nReturn the points per part.`,
  { label: 'draft:v1', phase: 'Draft', schema: PARTS_SCHEMA })
log(`Rubric v1: ${v1.parts.map(p => `${p.label} ${p.points}`).join(' · ')}`)

// ---------- Council + field test ----------
phase('Council')
const FILES = `${SRC} Also read in ${W}: Solutions.md, Solution methods.md, findings.md (what readers saw in ${SAMPLE.length} random submissions), Rubric v1.md (the draft). The rubric will be applied by a Claude grading bot reading one scanned PDF at a time, with TA approval. ${PRIVACY}`
const ROLES = [
  { key: 'lecturer', name: 'the lecturer, also an assessment expert', brief: 'For each part: what skill it tests and what a student must show. Where is v1 too lenient or harsh, misweighted, or teaching the wrong thing? Which mistakes are conceptual vs cosmetic? What must a final answer look like formally? Propose a one-line Hebrew comment for each common mistake. Vote on the open decisions.' },
  { key: 'ta', name: 'an experienced TA who will grade every submission, also designing the grading bot', brief: 'Find every place two graders (or a bot) would score the same work differently: vague wording, overlapping rules, double penalties, judgment calls, missing cases (illegible, crossed-out, two answers, answer in another part, miscopied question, answers only, work spread over pages, wrong file). Propose mechanical rules, a checking order, and a "flag for a human" list.' },
  { key: 'weak', name: 'a struggling student', brief: 'For EVERY part, list plausible wrong or half-right answers and reasoning paths, including ones not in findings.md (aim for 4+ per part), what the final answer would look like, and what partial credit is fair.' },
  { key: 'strong', name: 'a strong student who is also a careful mathematician', brief: 'For every part: all correct alternative methods and equivalent final forms (other parametrizations, decimal vs fraction, other counterexamples, condition vs parametric form) that v1 might wrongly penalize. Recompute every answer and claim in Solutions.md and Rubric v1.md and report any error.' },
  { key: 'appeals', name: 'the student-appeals officer', brief: 'Find unfairness: double penalties for one mistake, harsh notation penalties when the math is right, inconsistency between similar parts, rules that punish shown work more than bare answers, anything a student would win on appeal. Propose an error-carried-forward policy and caps.' },
]
const REPORT = { type: 'object', properties: {
  issues: { type: 'array', items: { type: 'object', properties: {
    part: { type: 'string' }, problem: { type: 'string' }, proposal: { type: 'string', description: 'exact rule, points, wording' },
    severity: { type: 'string', enum: ['major', 'medium', 'minor'] } }, required: ['part', 'problem', 'proposal', 'severity'] } },
  new_cases: { type: 'array', items: { type: 'object', properties: {
    part: { type: 'string' }, case: { type: 'string' }, points: { type: 'string' }, why: { type: 'string' } }, required: ['part', 'case', 'points', 'why'] } },
  open_decisions: { type: 'string' },
}, required: ['issues', 'new_cases', 'open_decisions'] }

const councilP = parallel(ROLES.map(r => () => agent(
  `You are on a rubric council as ${r.name}.\n${FILES}\n\nTask: ${r.brief}\nGo through every part (${PARTS.join(', ')}) and the global rules. Be concrete: every proposal must be pasteable into the rubric.`,
  { label: `council:${r.key}`, phase: 'Council', schema: REPORT })))

const GRADE = { type: 'object', properties: {
  grades: { type: 'array', items: { type: 'object', properties: {
    number: { type: 'string' }, part: { type: 'string', enum: PARTS }, points: { type: 'number' }, rule: { type: 'string' },
  }, required: ['number', 'part', 'points', 'rule'] } },
  gaps: { type: 'array', items: { type: 'string' }, description: 'every moment the rubric did not say what to do, or was ambiguous' },
}, required: ['grades', 'gaps'] }
const fieldP = parallel([1, 2].map(i => () => agent(
  `You are TA #${i}, field-testing ${W}\\Rubric v1.md. Another TA grades the same work independently. ${SRC}\n${PAGES_HOW}\nGrade strictly by Rubric v1 these submissions that were not in the sample: ${FRESH.join(' ')}. One row per submission and part: points and the rule you applied. Then list every gap or ambiguity you hit. ${PRIVACY}`,
  { label: `field:TA${i}`, phase: 'Council', model: 'sonnet', schema: GRADE })))

const [council, field] = await Promise.all([councilP, fieldP])
const C = council.map((c, i) => c && ({ role: ROLES[i].key, ...c })).filter(Boolean)
const F = field.filter(Boolean)
const diffs = []
if (F.length === 2) {
  for (const g of F[0].grades) {
    const o = F[1].grades.find(x => x.number === g.number && x.part === g.part)
    if (o && o.points !== g.points) diffs.push({ number: g.number, part: g.part, ta1: [g.points, g.rule], ta2: [o.points, o.rule] })
  }
}
const totals = FRESH.map(n => `${n}: ${F.map(t => t.grades.filter(g => g.number === n).reduce((s, g) => s + g.points, 0)).join('/')}`).join('; ')
log(`Field test: ${diffs.length} part-level disagreements. Totals TA1/TA2: ${totals}`)
const fieldText = JSON.stringify({ totals, disagreements: diffs, gaps: F.map(t => t.gaps) })

// ---------- Vote on contested points only ----------
phase('Vote')
const CONTESTED = { type: 'object', properties: { points: { type: 'array', items: { type: 'object', properties: {
  id: { type: 'string' }, question: { type: 'string', description: 'the decision, neutral' }, options: { type: 'array', items: { type: 'string' } },
}, required: ['id', 'question', 'options'] } } }, required: ['points'] }
const contested = await agent(
  `You moderate a rubric council. From the reports and the field test below, list the decisions where members disagree or the field test shows graders diverge, plus the open decisions of Rubric v1 (at most 12, most consequential first). Each: a neutral question and 2-4 concrete options (exact points/rules). Proposals nobody contests are NOT listed: they are adopted.\n\nReports: ${JSON.stringify(C)}\n\nField test: ${fieldText}`,
  { label: 'moderator', phase: 'Vote', schema: CONTESTED })
const contestedText = JSON.stringify(contested.points)
const VOTE = { type: 'object', properties: { votes: { type: 'array', items: { type: 'object', properties: {
  id: { type: 'string' }, choice: { type: 'string' }, why: { type: 'string', description: 'one or two sentences, from your role, thinking of the actual student, the TA at submission 400, and an appeal' },
}, required: ['id', 'choice', 'why'] } } }, required: ['votes'] }
const votes = (await parallel(ROLES.map(r => () => agent(
  `You are ${r.name} on the rubric council. Vote on each contested decision below, from your role. You may propose a better option. Disagree where you disagree; a council that agrees on everything is useless.\n\n${contestedText}`,
  { label: `vote:${r.key}`, phase: 'Vote', model: 'sonnet', schema: VOTE })))).map((v, i) => v && ({ role: ROLES[i].key, ...v })).filter(Boolean)

// ---------- Write ----------
phase('Write')
const OUT = `${W}\\Rubric.md`
await agent(
  `You chair the rubric council. Write the final rubric to ${OUT} (Write tool), in Hebrew, following the structure in ${args.template} exactly (read it first). Be exhaustive: every case, caveat and exception; there is no length limit.\n${FILES}\n\nAdopt every uncontested proposal from the reports; decide each contested point by the votes (record dissent); turn every field-test gap into an explicit rule or table row.\n\nCouncil reports: ${JSON.stringify(C)}\n\nField test: ${fieldText}\n\nContested points: ${contestedText}\n\nVotes: ${JSON.stringify(votes)}\n\nReturn 5 lines: the main changes from v1.`,
  { label: 'chair:write', phase: 'Write' })

// ---------- Critique ----------
phase('Critique')
const CRIT = { type: 'object', properties: { major: { type: 'array', items: { type: 'string' } }, minor: { type: 'array', items: { type: 'string' } } }, required: ['major', 'minor'] }
const CRITICS = [
  { key: 'student', model: 'sonnet', lens: 'a student receiving this grade: unfair, unclear or appealable rules, double penalties, confusing comments' },
  { key: 'ta', model: 'sonnet', lens: 'a TA (or bot) at submission 400: ambiguous rules, rules that contradict each other or the template, missing cases, judgment calls' },
  { key: 'lecturer', lens: 'the lecturer and a mathematician: rules that reward answers not showing the skill, misweighted parts, any wrong answer or equivalent form, points that do not add up' },
]
for (let round = 1; round <= 2; round++) {
  const crits = (await parallel(CRITICS.map(c => () => agent(
    `Critique ${OUT} as ${c.lens}. Sources: questions.md and Solutions.md in ${W}; structure rules: ${args.template}. List major problems (wrong or inconsistent grades, wrong math, template broken) and minor ones, each with section and fix. Nothing to report = empty lists.`,
    { label: `critic:${c.key}:${round}`, phase: 'Critique', model: c.model, schema: CRIT })))).filter(Boolean)
  const major = crits.flatMap((c, i) => c.major.map(m => `[${CRITICS[i].key}] ${m}`))
  const minor = crits.flatMap((c, i) => c.minor.map(m => `[${CRITICS[i].key}] ${m}`))
  log(`Critique ${round}: ${major.length} major, ${minor.length} minor`)
  if (!major.length && !minor.length) break
  await agent(
    `You chair the rubric council. Revise ${OUT} in place for these critiques. Fix every major one, and every minor one that makes the rubric more complete or more precise. A critique you reject goes under ⚠ in the open-decisions section with one line why.\nMAJOR:\n${major.join('\n')}\nMINOR:\n${minor.join('\n')}\nReturn what you changed, briefly.`,
    { label: `chair:revise:${round}`, phase: 'Critique' })
  if (!major.length) break
}

// ---------- Check ----------
phase('Check')
const check = await agent(
  `Final check of ${OUT} against ${args.template}, ${W}\\questions.md and ${W}\\Solutions.md: (1) part maximums sum to exactly 100 and no row exceeds its part; (2) every part (${PARTS.join(', ')}) has a table; (3) every stated answer matches Solutions.md; (4) no names, ID numbers or emails anywhere in ${W}\\*.md; (5) the open-decisions section exists; (6) Solution methods.md does not contradict the rubric on how out-of-scope methods are scored (if it does, make it point to the rubric). Fix small problems directly. Return: what you checked, fixed, and what is still open.`,
  { label: 'check', phase: 'Check', model: 'sonnet' })

return { work: W, parts: v1.parts, field_test_totals: totals, field_test_disagreements: diffs.length, contested: contested.points.length, check }
