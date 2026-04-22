"""État session partagé — acting user pour les writes.

Vit pour la durée du process MCP (qui dure une session Claude Desktop).
Pas de persistence disque volontairement : à chaque redémarrage, il faut
redéfinir l'acting user. C'est un garde-fou contre les surprises.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class SessionState:
    """État mutable du serveur MCP pendant sa durée de vie."""

    acting_user_id: str | None = None


# Instance unique pour le process
_state = SessionState()


def get_state() -> SessionState:
    return _state


def require_acting_user() -> str:
    """Retourne l'acting user ou lève une erreur claire."""
    if _state.acting_user_id is None:
        raise RuntimeError(
            "Aucun acting_user défini. Appelle set_acting_user(user_id=...) "
            "avant toute opération d'écriture. Utilise list_profiles() pour "
            "voir les user_id disponibles."
        )
    return _state.acting_user_id
