"""Logica compartida para derivar el nombre de repositorio y de controlador a partir del nombre de API del Excel."""


def parse_api_name(api_name: str, api_type: str) -> dict | None:
    """Devuelve {'repo_name': ..., 'name_part': ...} o None si el nombre no es reconocible."""
    parts = api_name.split()
    if not parts:
        return None
    prefix = parts[0]

    if prefix == 'API':
        if len(parts) > 2 and parts[1] == 'UX' and api_type == 'UX':
            code = parts[2].lower()
            name = '-'.join(parts[3:-1]).lower()
            if not name:
                return None
            return {'repo_name': f"channel-{code}-{name}", 'name_part': name}
        if len(parts) > 2 and parts[1] == 'BS' and api_type == 'BS':
            name = '-'.join(parts[2:-1]).lower()
            if not name:
                return None
            return {'repo_name': f"business-{name}", 'name_part': name}
    elif prefix == 'AsyncAPI' and api_type == 'Async':
        if len(parts) > 2:
            code = parts[1].lower()
            name = '-'.join(parts[2:-1]).lower()
            if name:
                return {'repo_name': f"asyncapi-{code}-{name}", 'name_part': name}

    return None


def generate_repo_name(api_name: str, api_type: str) -> str | None:
    parsed = parse_api_name(api_name, api_type)
    return parsed['repo_name'] if parsed else None


def controller_name(name_part: str) -> str:
    return ' '.join(word.capitalize() for word in name_part.split('-'))
