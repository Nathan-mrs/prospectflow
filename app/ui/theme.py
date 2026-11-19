"""Tema visual: fonte Inter, tokens de cor (claro/escuro) e classes utilitárias.

As cores ficam em variáveis CSS. O modo escuro é ativado pelo Quasar com a
classe ``body--dark``; redefinimos os tokens nela, então todo componente que
usa ``var(--pf-*)`` troca de tema sozinho.
"""

from __future__ import annotations

from nicegui import ui

ACCENT = "#4F46E5"

_HEAD = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --pf-bg: #FAFAFA;
  --pf-surface: #FFFFFF;
  --pf-surface-2: #F4F4F5;
  --pf-border: #E4E4E7;
  --pf-text: #18181B;
  --pf-muted: #71717A;
  --pf-accent: #4F46E5;
  --pf-accent-soft: #EEF2FF;
  --pf-success: #16A34A; --pf-success-soft: #DCFCE7;
  --pf-warning: #D97706; --pf-warning-soft: #FEF3C7;
  --pf-danger: #DC2626;  --pf-danger-soft: #FEE2E2;
  --pf-shadow: 0 1px 2px rgba(16,24,40,.04), 0 1px 3px rgba(16,24,40,.06);
}
body.body--dark {
  --pf-bg: #09090B;
  --pf-surface: #131316;
  --pf-surface-2: #1C1C21;
  --pf-border: #27272A;
  --pf-text: #FAFAFA;
  --pf-muted: #A1A1AA;
  --pf-accent: #818CF8;
  --pf-accent-soft: rgba(129,140,248,.14);
  --pf-success: #4ADE80; --pf-success-soft: rgba(74,222,128,.12);
  --pf-warning: #FBBF24; --pf-warning-soft: rgba(251,191,36,.12);
  --pf-danger: #F87171;  --pf-danger-soft: rgba(248,113,113,.12);
  --pf-shadow: 0 1px 2px rgba(0,0,0,.4);
}
body, .q-field, .q-btn, .q-table, .q-item { font-family: 'Inter', system-ui, sans-serif; }
body { background: var(--pf-bg); color: var(--pf-text); -webkit-font-smoothing: antialiased; }
.q-header { background: var(--pf-surface) !important; color: var(--pf-text) !important;
            border-bottom: 1px solid var(--pf-border); }
.q-drawer { background: var(--pf-surface) !important; }
.q-drawer--bordered { border-color: var(--pf-border) !important; }

.pf-card { background: var(--pf-surface); border: 1px solid var(--pf-border); border-radius: 14px;
           box-shadow: var(--pf-shadow); }
.pf-muted { color: var(--pf-muted); }
.pf-title { font-size: 1.5rem; font-weight: 700; letter-spacing: -0.02em; }
.pf-subtitle { font-size: .95rem; color: var(--pf-muted); }
.pf-section { font-size: .8rem; font-weight: 600; text-transform: uppercase; letter-spacing: .06em;
              color: var(--pf-muted); }

.pf-nav-item { border-radius: 10px; color: var(--pf-muted); font-weight: 500; min-height: 40px; }
.pf-nav-item:hover { background: var(--pf-surface-2); color: var(--pf-text); }
.pf-nav-item.pf-active { background: var(--pf-accent-soft); color: var(--pf-accent); }

.pf-badge { display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 999px;
            font-size: .75rem; font-weight: 600; line-height: 1.6; white-space: nowrap; }
.pf-dot { width: 7px; height: 7px; border-radius: 999px; display: inline-block; }

.pf-dropzone .q-uploader { width: 100%; box-shadow: none; border: 2px dashed var(--pf-border);
                           border-radius: 14px; background: var(--pf-surface-2); }
.pf-dropzone .q-uploader:hover { border-color: var(--pf-accent); }
.pf-dropzone .q-uploader__header { background: transparent; color: var(--pf-text); }

.pf-table { background: var(--pf-surface); border: 1px solid var(--pf-border); border-radius: 12px;
            box-shadow: none; }
.pf-table thead tr th { font-weight: 600; color: var(--pf-muted); }
.q-stepper { background: transparent; box-shadow: none; }
.q-stepper__header { border-bottom: 1px solid var(--pf-border); }
.pf-rank { border-collapse: collapse; }
.pf-rank th, .pf-rank td { padding: 8px 10px; border-bottom: 1px solid var(--pf-border); white-space: nowrap; }
.pf-rank th { color: var(--pf-muted); font-weight: 600; font-size: 12px; }
.pf-rank tbody tr:last-child td { border-bottom: none; }
</style>
"""

def install_theme() -> None:
    """Registra fonte e CSS para todas as páginas (chamar uma vez na inicialização)."""
    ui.add_head_html(_HEAD, shared=True)


def apply_page_theme() -> None:
    """Configura cores do Quasar na página atual."""
    ui.colors(primary=ACCENT, secondary="#64748B", positive="#16A34A", negative="#DC2626",
              warning="#D97706", info="#0EA5E9")
