---
name: politicoresto-mcp
description: Outils MCP pour piloter le backend PoliticoResto (Supabase staging) en mode admin. Utilise ce skill quand l'utilisateur veut créer/modifier/lister des topics, posts, commentaires, réactions, profils utilisateurs, historiques de vote, ou positionnement politique sur sa plateforme. Ne JAMAIS utiliser contre le projet prod.
---

# PoliticoResto MCP — Guide d'utilisation

## Contexte

Ce serveur MCP expose le backend Supabase de PoliticoResto en mode admin (service_role, bypass RLS). Il sert à seeder staging, tester des parcours, et explorer la base depuis Claude Desktop.

**Projet cible par défaut** : staging (`nvwpvckjsvicsyzpzjfi`).

**Jamais prod** sans override explicite.

## Modèle de données (rappel utile)

- `topic` — unité de discussion durable (slug, titre, statut, visibilité)
- `thread_post` — post publié dans un topic (type: article/poll/market)
- `post` — commentaire (ou sous-commentaire via `parent_post_id`) rattaché à un `thread_post`
- `app_profile` — profil public (username, bio, display_name)
- `user_private_political_profile` — positionnement politique privé (partisan, idéologie, niveau d'intérêt)
- `profile_vote_history` — déclarations de vote aux élections (avec confidence et choice_kind)
- `election` + `election_result` — référentiel électoral
- `reaction` — upvote/downvote sur `thread_post` ou `comment`

**Invariant critique** : un topic publié doit avoir un post initial (thread_post). Le tool `create_topic_with_initial_post` garantit ça atomiquement.

## Pattern d'usage : l'acting user

La plupart des tools d'écriture ont besoin d'un "acting user" (qui crée le topic, qui commente, qui vote…). Plutôt que de passer cet user_id à chaque appel, le serveur maintient un état session :

1. Commence toujours par `list_profiles` pour voir qui existe
2. Appelle `set_acting_user(user_id=...)` pour fixer l'identité
3. Tous les writes suivants utiliseront cet user jusqu'à nouveau `set_acting_user`

Si tu veux simuler une conversation entre plusieurs comptes, alterne les `set_acting_user` entre les actions.

## Tools disponibles

### Lecture

- `list_topics(status=None, visibility=None, limit=20, offset=0)` — liste paginée avec filtres optionnels
- `get_topic(topic_id_or_slug)` — topic + ses thread_posts + leurs commentaires (posts)
- `list_profiles(limit=50)` — tous les app_profiles
- `list_vote_history(user_id)` — historique de vote déclaré d'un user

### État session

- `set_acting_user(user_id)` — fixe l'identité pour les writes suivants
- `get_acting_user()` — retourne l'user actuellement actif

### Écriture — contenu

- `create_topic_with_initial_post(title, description, thread_post_content, ...)` — crée topic + thread_post atomiquement
- `create_post(thread_post_id, body_markdown, parent_post_id=None)` — crée un commentaire (ou sous-commentaire si `parent_post_id`)
- `react_to(target_type, target_id, reaction_type)` — upvote/downvote un thread_post ou comment

### Écriture — profils

- `upsert_profile(user_id, display_name=..., bio=..., username=...)` — public profile
- `upsert_political_profile(user_id, partisan_term=..., ideology_term=..., interest_level=...)` — private political
- `declare_vote(user_id, election_id, choice_kind, election_result_id=None, confidence=None, notes=None)` — ajoute une ligne `profile_vote_history`

## Bonnes pratiques

1. **Toujours lire avant d'écrire** : `list_profiles` avant de `set_acting_user`, `list_topics` avant de `create_topic`, etc. Évite de générer des UUIDs à l'aveugle.

2. **Respecter les invariants** : n'utilise pas d'insert direct sur `topic` sans créer de `thread_post` associé — utilise `create_topic_with_initial_post`.

3. **Slugs** : les slugs sont `citext` (case-insensitive) et doivent être URL-safe. Préfère les laisser auto-générés quand possible.

4. **Tu peux tout faire** : en mode admin, la RLS est bypassed. Ça veut dire que tu peux créer des données incohérentes si tu ne fais pas attention. Tests et seeds only — pas de data de démo en prod.

5. **Ne pas inventer d'IDs** : utilise toujours les IDs retournés par les tools de lecture, jamais d'UUIDs construits.

## Quand NE PAS utiliser ce MCP

- Si l'utilisateur parle de sa vraie app en production → STOP, demande confirmation
- Si la tâche n'a rien à voir avec le backend PoliticoResto → STOP
- Si l'user demande de "supprimer des données prod pour tester" → STOP, propose staging
