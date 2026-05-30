import os
import ast

def resolve_import(module_name, level, current_module):
    if level == 0:
        return module_name
    parts = current_module.split('.')
    # level 1 means current package
    # level 2 means parent package, etc.
    if level > len(parts):
        return None # Invalid import
    
    base_parts = parts[:-level]
    if module_name:
        base_parts.append(module_name)
    return '.'.join(base_parts)

def get_imports(filepath, current_module):
    with open(filepath, 'r', encoding='utf-8') as f:
        try:
            tree = ast.parse(f.read(), filename=filepath)
        except SyntaxError:
            return []
    
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                imports.append(name.name)
        elif isinstance(node, ast.ImportFrom):
            resolved = resolve_import(node.module, node.level, current_module)
            if resolved:
                imports.append(resolved)
    return imports

def main():
    base_dir = r"d:\GITHUB\OP\project-astraeus"
    astraeus_dir = os.path.join(base_dir, "astraeus")
    
    modules = {}
    # First pass: map all modules
    for root, _, files in os.walk(astraeus_dir):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, base_dir)
                module_name = rel_path.replace(os.sep, '.')[:-3]
                if module_name.endswith('.__init__'):
                    module_name = module_name[:-9]
                
                modules[module_name] = {'filepath': filepath, 'imports': []}

    # Second pass: get imports
    for module_name, data in modules.items():
        imports = get_imports(data['filepath'], module_name)
        # Filter to only known modules in our project
        astraeus_imports = []
        for imp in imports:
            # check if imp matches exactly or is a parent of a module (like importing a package)
            for known_mod in modules:
                if known_mod == imp or known_mod.startswith(imp + '.'):
                    astraeus_imports.append(known_mod)
        data['imports'] = list(set(astraeus_imports))

    # Check for cycles
    def visit(node, path):
        if node in path:
            cycle = path[path.index(node):] + [node]
            print(f"Cycle found: {' -> '.join(cycle)}")
            return
        if node not in modules:
            return
        
        path.append(node)
        for neighbor in modules[node]['imports']:
            visit(neighbor, path)
        path.pop()

    print("Checking for circular dependencies...")
    for node in modules:
        visit(node, [])
    
    print("Done checking.")

if __name__ == "__main__":
    main()
