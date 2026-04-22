# PoliticoResto MCP — Admin Server

MCP server Python/FastMCP qui expose les opérations CRUD de PoliticoResto à Claude Desktop, en mode **admin local uniquement**.

## ⚠️ Ce que ce serveur est — et n'est PAS

**EST** :
- Un outil de **seed/test/exploration** de staging
- Utilisable uniquement en **local** via Claude Desktop (transport stdio)
- Authentifié avec la `SUPABASE_SERVICE_ROLE_KEY`, qui bypass RLS totalement

**N'EST PAS** :
- Un serveur accessible publiquement
- Un backend pour utilisateurs finaux
- Sûr à déployer en HTTP tel quel — la service_role key donne les pleins pouvoirs

Si un jour tu veux ouvrir au public, il faudra un **deuxième** MCP server avec OAuth + JWT utilisateur + RLS active. Ce serveur-ci restera un outil de dev.

## Configuration

1. Copie `.env.example` vers `.env`
2. Renseigne les deux variables :
   - `SUPABASE_PROJECT_URL` — URL de ton projet Supabase (staging par défaut)
   - `SUPABASE_SERVICE_ROLE_KEY` — service role key (depuis Supabase Dashboard → Settings → API)

La service role key bypass la RLS. Elle ne doit **jamais** être commitée.

## Installation

```bash
# Crée un venv et installe
python -m venv .venv
source .venv/bin/activate  # ou .venv\Scripts\activate sur Windows
pip install -e .
```

## Branchement dans Claude Desktop

Ajoute dans `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) ou `%APPDATA%\Claude\claude_desktop_config.json` (Windows) :

```json
{
  "mcpServers": {
    "politicoresto": {
      "command": "/chemin/vers/politicoresto-mcp/.venv/bin/python",
      "args": ["-m", "politicoresto_mcp"],
      "env": {
        "SUPABASE_PROJECT_URL": "https://nvwpvckjsvicsyzpzjfi.supabase.co",
        "SUPABASE_SERVICE_ROLE_KEY": "eyJ..."
      }
    }
  }
}
```

Redémarre Claude Desktop. Tu dois voir le serveur "politicoresto" apparaître avec ses tools.

## Garde-fou prod

Par défaut, le serveur refuse de démarrer si `SUPABASE_PROJECT_URL` pointe sur le projet prod (`gzdpisxkavpyfmhsktcg`). Pour forcer (vraiment ? réfléchis), ajoute `POLITICORESTO_ALLOW_PROD=yes_i_know`.

## Tools disponibles

Voir [SKILL.md](./SKILL.md) pour la liste complète et les conventions d'usage.

## Développement

```bash
# Test que le serveur démarre
python -m politicoresto_mcp

# Lance l'inspecteur MCP officiel (UI web pour débugger)
npx @modelcontextprotocol/inspector python -m politicoresto_mcp
```
