import argparse
import sys
import urllib.request
import json
from urllib.error import URLError, HTTPError
from collections import deque

class DependencyGraph:
    def __init__(self):
        self.graph = {}
        self.visited = set()
        self.cycle_detected = False
        self.cycle_edges = set() 
        
    def fetch_package_data(self, package_name):
        try:
            url = f"https://registry.npmjs.org/{package_name}"
            with urllib.request.urlopen(url) as response:
                data = response.read().decode('utf-8')
                return json.loads(data)
        except Exception as e:
            print(f"Error fetching {package_name}: {e}")
            return None
    
    def get_direct_dependencies(self, package_name, version):
        package_data = self.fetch_package_data(package_name)
        if not package_data:
            return {}
            
        versions = package_data.get('versions', {})
        if version in versions:
            return versions[version].get('dependencies', {})
        
        print(f"Version {version} not found for {package_name}")
        return {}
    
    def build_graph_from_file(self, file_path, root_package):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            for line in lines:
                line = line.strip()
                if not line or ':' not in line:
                    continue
                
                package, deps_str = line.split(':', 1)
                package = package.strip()
                dependencies = [dep.strip() for dep in deps_str.split() if dep.strip()]
                self.graph[package] = dependencies
            
            return root_package in self.graph
            
        except Exception as e:
            print(f"Error reading file: {e}")
            return False
    
    def build_dependency_graph_real(self, package_name, version, max_depth):
        queue = deque()
        queue.append((package_name, version, 0, [package_name]))
        self.visited.add(package_name)
        
        while queue:
            current_package, current_version, depth, path = queue.popleft()
            
            if depth > max_depth:
                continue
                
            dependencies = self.get_direct_dependencies(current_package, current_version)
            self.graph[current_package] = list(dependencies.keys())
            
            for dep_name, dep_version in dependencies.items():
                if dep_name not in self.visited:
                    if dep_name in path:
                        cycle_path = ' -> '.join(path) + ' -> ' + dep_name
                        print(f"Cyclic dependency detected: {cycle_path}")
                        self.cycle_detected = True
                        self.cycle_edges.add((current_package, dep_name))
                        continue
                    
                    self.visited.add(dep_name)
                    clean_version = self.clean_version(dep_version)
                    new_path = path + [dep_name]
                    queue.append((dep_name, clean_version, depth + 1, new_path))
    
    def build_dependency_graph_test(self, root_package, max_depth):
        queue = deque()
        queue.append((root_package, 0, [root_package]))
        self.visited.add(root_package)
        
        while queue:
            current_package, depth, path = queue.popleft()
            
            if depth > max_depth:
                continue
                
            if current_package not in self.graph:
                continue
                
            for dep_name in self.graph[current_package]:
                if dep_name not in self.visited:
                    if dep_name in path:
                        cycle_path = ' -> '.join(path) + ' -> ' + dep_name
                        print(f"Cyclic dependency detected: {cycle_path}")
                        self.cycle_detected = True
                        self.cycle_edges.add((current_package, dep_name))
                        continue
                    
                    self.visited.add(dep_name)
                    new_path = path + [dep_name]
                    queue.append((dep_name, depth + 1, new_path))
    
    def clean_version(self, version_str):
        import re
        return re.sub(r'^[\^~><=]*', '', version_str)
    
    def print_ascii_tree(self, root):
        stack = [(root, "", True, set())]
        
        while stack:
            node, prefix, is_last, visited = stack.pop()
            
            if node in visited:
                print(prefix + ("└── " if is_last else "├── ") + node + " [CYCLE]")
                continue
                
            print(prefix + ("└── " if is_last else "├── ") + node)
            
            new_visited = visited.copy()
            new_visited.add(node)
            new_prefix = prefix + ("    " if is_last else "│   ")
            
            children = self.graph.get(node, [])
            for i, child in enumerate(reversed(children)):
                is_last_child = (i == 0)
                if (node, child) in self.cycle_edges:
                    stack.append((child, new_prefix, is_last_child, new_visited))
                else:
                    stack.append((child, new_prefix, is_last_child, new_visited))
    
    def get_dependency_order(self):
        if self.cycle_detected:
            print("Cannot determine installation order due to cyclic dependencies")
            return []
        
        in_degree = {}
        for node in self.visited:  # Только для посещенных узлов
            in_degree[node] = 0
            
        for node in self.visited:
            for neighbor in self.graph.get(node, []):
                if neighbor in self.visited:
                    in_degree[neighbor] += 1
        
        queue = deque()
        for node in self.visited:
            if in_degree[node] == 0:
                queue.append(node)

        result = []
        while queue:
            node = queue.popleft()
            result.append(node)
            
            for neighbor in self.graph.get(node, []):
                if neighbor in self.visited:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

        if len(result) != len(self.visited):
            print("Warning: Some dependencies could not be ordered (possible cycles)")
            
        return result

def main():
    parser = argparse.ArgumentParser(
        description="Dependency graph visualization tool"
    )

    parser.add_argument("--package", type=str, required=True, help="Package name")
    parser.add_argument("--repo", type=str, required=True, help="Repository URL or file path")
    parser.add_argument("--test-mode", type=str, choices=["true", "false"], required=True, help="Test mode")
    parser.add_argument("--version", type=str, help="Package version")
    parser.add_argument("--output", type=str, default="graph.png", help="Output file")
    parser.add_argument("--ascii-tree", type=str, choices=["true", "false"], default="false", help="ASCII tree output")
    parser.add_argument("--max-depth", type=int, default=10, help="Maximum depth")

    args = parser.parse_args()

    print("Configuration parameters:")
    for key, value in vars(args).items():
        print(f"  {key}: {value}")
    print()

    graph = DependencyGraph()
    
    if args.test_mode == "true":
        print("TEST MODE: Building graph from file")
        
        if graph.build_graph_from_file(args.repo, args.package):
            print(f"Direct dependencies of {args.package}:")
            direct_deps = graph.graph.get(args.package, [])
            for dep in direct_deps:
                print(f"  - {dep}")
            print()
            
            graph.build_dependency_graph_test(args.package, args.max_depth)
            
            print(f"Full dependency graph built for {args.package}")
            print(f"Total packages in file: {len(graph.graph)}")
            print(f"Packages reachable from {args.package}: {len(graph.visited)}")
            
            if graph.cycle_detected:
                print("Cyclic dependencies found!")
            
            if args.ascii_tree == "true":
                print(f"Dependency tree for {args.package}:")
                graph.print_ascii_tree(args.package)
            
            print("Installation order:")
            order = graph.get_dependency_order()
            if order:
                for i, package in enumerate(order, 1):
                    print(f"  {i}. {package}")
            
            print("\nComplete dependency graph structure:")
            for package in sorted(graph.visited):  # Только достижимые узлы
                deps = graph.graph.get(package, [])
                if deps:
                    print(f"  {package} -> {', '.join(deps)}")
                else:
                    print(f"  {package} -> (no dependencies)")
                
        else:
            print("Error building graph from file")
            sys.exit(1)
            
    else:
        if not args.version:
            print("Error: version required for real mode")
            sys.exit(1)
            
        print("REAL MODE: Fetching from npm registry")
        
        direct_deps = graph.get_direct_dependencies(args.package, args.version)
        print(f"Direct dependencies of {args.package}@{args.version}:")
        for dep_name, dep_version in direct_deps.items():
            print(f"  - {dep_name}: {dep_version}")
        print()
        
        graph.build_dependency_graph_real(args.package, args.version, args.max_depth)
        
        print(f"Full dependency graph built for {args.package}@{args.version}")
        print(f"Total packages: {len(graph.graph)}")
        
        if graph.cycle_detected:
            print("Cyclic dependencies found!")
        
        if args.ascii_tree == "true":
            print(f"Dependency tree:")
            graph.print_ascii_tree(args.package)
        
        print("Installation order:")
        order = graph.get_dependency_order()
        if order:
            for i, package in enumerate(order, 1):
                print(f"  {i}. {package}")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)