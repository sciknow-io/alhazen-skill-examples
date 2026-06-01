import { execFile } from 'child_process';
import { promisify } from 'util';
import path from 'path';

const execFileAsync = promisify(execFile);

// SCILIT_SKILL_ROOT: absolute path to the scientific-literature skill dir (standalone demo)
// PROJECT_ROOT: absolute path to skillful-alhazen root (used when installed)
// NOTEBOOK_SCRIPT_PATH: override for typedb_notebook.py location
const SKILL_ROOT = process.env.SCILIT_SKILL_ROOT;
const PROJECT_ROOT = process.env.PROJECT_ROOT || path.resolve(process.cwd());

const SCILIT_SCRIPT = SKILL_ROOT
  ? path.join(SKILL_ROOT, 'scientific_literature.py')
  : path.join(PROJECT_ROOT, '.claude/skills/scientific-literature/scientific_literature.py');

const NOTEBOOK_SCRIPT = process.env.NOTEBOOK_SCRIPT_PATH
  || path.join(PROJECT_ROOT, '.claude/skills/typedb-notebook/typedb_notebook.py');

// All scilit commands run from PROJECT_ROOT: the semantic commands (`map`, embed,
// cluster) import skillful_alhazen + umap/hdbscan/qdrant which live in the MAIN
// project venv, not the scilit sub-venv. Read commands use typedb-driver which the
// main venv also has, so PROJECT_ROOT is the correct cwd for every command.
const CWD = PROJECT_ROOT;

async function runScilit(args: string[]): Promise<unknown> {
  const { stdout } = await execFileAsync(
    'uv',
    ['run', 'python', SCILIT_SCRIPT, ...args],
    {
      cwd: CWD,
      maxBuffer: 10 * 1024 * 1024,
      env: { ...process.env, TYPEDB_DATABASE: 'alhazen_notebook' },
    }
  );
  return JSON.parse(stdout);
}

async function runNotebook(args: string[]): Promise<unknown> {
  const { stdout } = await execFileAsync(
    'uv',
    ['run', 'python', NOTEBOOK_SCRIPT, ...args],
    {
      cwd: CWD,
      maxBuffer: 10 * 1024 * 1024,
      env: { ...process.env, TYPEDB_DATABASE: 'alhazen_notebook' },
    }
  );
  return JSON.parse(stdout);
}

// --- Typed interfaces ---------------------------------------------------------

export interface Corpus {
  id: string;
  name: string;
  description?: string;
  'logical-query'?: string;
}

export interface Paper {
  id: string;
  name?: string;
  doi?: string;
  year?: number;
  'abstract-text'?: string;
  pmid?: string;
  journal?: string;
  'source-uri'?: string;
}

export interface PaperNote {
  id: string;
  name?: string;
  content?: string;
}

export interface PaperDetail {
  success: boolean;
  paper: Paper;
  keywords: string[];
  notes: PaperNote[];
  pdf_artifacts: Array<{ id: string; 'source-uri'?: string; 'cache-path'?: string; 'file-size'?: number }>;
}

export interface MapItem {
  paper_id: string;
  x: number;
  y: number;
  cluster: number;
  title?: string;
  year?: number;
  corpus_ids: string[];
  facets: Record<string, string>;
}

export interface MapData {
  success: boolean;
  count: number;
  num_clusters: number;
  collection_ids: string[];
  items: MapItem[];
}

export interface FacetingNoteSummary {
  id: string;
  name: string;
  has_content: boolean;
  content_preview?: string;
  collections: Array<{ id: string; name: string }>;
}

export interface FacetingNoteDetail {
  success: boolean;
  note_id: string;
  name: string;
  script?: string;
  config?: unknown;
  content?: string;
}

export interface InvestigationCorpusRef {
  id: string;
  name?: string;
}

export interface InvestigationSummary {
  id: string;
  name?: string;
  purpose?: string;
  status?: string;
  'created-at'?: string;
  corpus?: InvestigationCorpusRef | null;
  phase_count?: number;
}

export interface InvestigationPhase {
  id: string;
  name?: string;
  content?: string;
  phase: string;
  'created-at'?: string;
  faceting_notes?: Array<{ id: string; name?: string }>;
}

export interface InvestigationDetail {
  success: boolean;
  id: string;
  name?: string;
  purpose?: string;
  status?: string;
  'created-at'?: string;
  corpus?: InvestigationCorpusRef | null;
  phases: InvestigationPhase[];
}

// --- Read endpoints (scilit CLI) ----------------------------------------------

export async function listCorpora(): Promise<{ collections: Corpus[]; count: number }> {
  return runScilit(['list-collections']) as Promise<{ collections: Corpus[]; count: number }>;
}

export async function listPapers(collectionId: string): Promise<{ papers: Paper[]; count: number; collection: string }> {
  return runScilit(['list', '--collection', collectionId]) as Promise<{
    papers: Paper[];
    count: number;
    collection: string;
  }>;
}

export async function getPaper(id: string): Promise<PaperDetail> {
  return runScilit(['show', '--id', id]) as Promise<PaperDetail>;
}

export async function getMap(opts?: { collectionIds?: string[]; all?: boolean; minClusterSize?: number }): Promise<MapData> {
  const args = ['map'];
  if (opts?.all) {
    args.push('--all');
  } else if (opts?.collectionIds) {
    for (const cid of opts.collectionIds) args.push('--collection', cid);
  }
  if (opts?.minClusterSize !== undefined) args.push('--min-cluster-size', String(opts.minClusterSize));
  return runScilit(args) as Promise<MapData>;
}

// --- Faceting-note endpoints (core typedb-notebook CLI) -----------------------

export async function listFacetingNotes(): Promise<{ notes: FacetingNoteSummary[]; count: number }> {
  return runNotebook(['list-pipeline-notes']) as Promise<{ notes: FacetingNoteSummary[]; count: number }>;
}

export async function getFacetingNote(id: string): Promise<FacetingNoteDetail> {
  return runNotebook(['show-pipeline-note', '--id', id]) as Promise<FacetingNoteDetail>;
}

export interface RunResult {
  success: boolean;
  note_id: string;
  // keyed by output name -> { attr, chars }
  outputs_written: Record<string, { attr: string; chars: number }>;
  outputs_not_persisted: Record<string, unknown>;
}

export async function runFacetingNote(id: string): Promise<RunResult> {
  return runNotebook(['run-pipeline-note', '--id', id]) as Promise<RunResult>;
}

// --- Investigation endpoints (scilit CLI) -------------------------------------

export async function listInvestigations(collectionId?: string): Promise<{ investigations: InvestigationSummary[]; count: number }> {
  const args = ['list-investigations'];
  if (collectionId) args.push('--collection', collectionId);
  return runScilit(args) as Promise<{ investigations: InvestigationSummary[]; count: number }>;
}

export async function getInvestigation(id: string): Promise<InvestigationDetail> {
  return runScilit(['show-investigation', '--id', id]) as Promise<InvestigationDetail>;
}
