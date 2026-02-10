import json

with open('app_perms.json', 'r', encoding='utf-8') as f:
    app_perms = json.load(f)

with open('graph_roles.json', 'r', encoding='utf-8') as f:
    graph_roles = json.load(f)

# Map ID to display name
role_map = {role['id']: role['value'] for role in graph_roles}

print("Current Application Permissions:")
for perm in app_perms:
    for access in perm.get('resourceAccess', []):
        name = role_map.get(access['id'], access['id'])
        print(f"- {name} ({access['type']})")
