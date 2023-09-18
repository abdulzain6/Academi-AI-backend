from typing import List, Tuple, Any, Optional
from RestrictedPython import safe_builtins
from RestrictedPython.Utilities import utility_builtins
from RestrictedPython.Limits import limited_builtins
import sys
import traceback
import io
import ast

safe_builtins_2 = {
    'abs': abs,
    'all': all,
    'any': any,
    'ascii': ascii,
    'bin': bin,
    'bool': bool,
    'bytearray': bytearray,
    'bytes': bytes,
    'callable': callable,
    'chr': chr,
    'divmod': divmod,
    'enumerate': enumerate,
    'filter': filter,
    'float': float,
    'format': format,
    'frozenset': frozenset,
    'hash': hash,
    'hex': hex,
    'id': id,
    'int': int,
    'isinstance': isinstance,
    'issubclass': issubclass,
    'iter': iter,
    'len': len,
    'list': list,
    'map': map,
    'max': max,
    'min': min,
    'next': next,
    'object': object,
    'oct': oct,
    'ord': ord,
    'pow': pow,
    'range': range,
    'repr': repr,
    'reversed': reversed,
    'round': round,
    'set': set,
    'slice': slice,
    'sorted': sorted,
    'str': str,
    'sum': sum,
    'super': super,
    'tuple': tuple,
    'type': type,
    'zip': zip,
}



class FinalStatefulSafeCodeEvaluator:
    def __init__(self, allowed_libraries: Optional[List[str]] = None):
        self.allowed_libraries = [
            'math', 'random', 'string', 'datetime', 'collections', 'itertools', 
            'functools', 'operator', 're', 'enum', 'heapq', 'bisect', 'array', 
            'weakref', 'types', 'copy', 'pprint', 'struct', 'decimal', 'fractions', 'numexpr'
        ] + allowed_libraries
        
        self.allowed_extra = allowed_libraries
        self.aliases = {}
        
    def get_allowed_libraries(self):
        return self.allowed_libraries

    def is_node_allowed(self, node, in_import=False) -> Tuple[bool, str]:
        if isinstance(node, ast.Import):
            for n in node.names:
                if not any(n.name.startswith(lib) for lib in self.allowed_libraries):
                    return False, f"Importing {n.name} is not allowed."
                if n.asname:
                    self.aliases[n.asname] = n.name
            return True, ""
        
        elif isinstance(node, ast.ImportFrom):
            module_parts = node.module.split('.') if node.module else []
            if not any(part in self.allowed_libraries for part in module_parts):
                return False, f"Importing from {node.module} is not allowed."
            for n in node.names:
                if n.asname:
                    self.aliases[n.asname] = n.name
            return True, ""
        
        elif isinstance(node, ast.Name):
            if in_import:
                if node.id in self.aliases:
                    original_name = self.aliases[node.id]
                    if not any(original_name.startswith(lib) for lib in self.allowed_libraries):
                        return False, f"Usage of {node.id} (alias for {original_name}) is not allowed."
                elif not any(node.id.startswith(lib) for lib in self.allowed_libraries):
                    return False, f"Usage of {node.id} is not allowed."
        
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id == '__import__':
                return False, "Using __import__ is not allowed."
        
        for child_node in ast.iter_child_nodes(node):
            allowed, message = self.is_node_allowed(child_node, isinstance(node, (ast.Import, ast.ImportFrom)))
            if not allowed:
                return False, message

        return True, ""
    
    def is_code_allowed(self, code: str) -> Tuple[bool, str]:
        tree = ast.parse(code, mode='exec')
        
        for node in tree.body:
            allowed, message = self.is_node_allowed(node)
            if not allowed:
                return False, message
            
        return True, "All lines are allowed."
    
    def wrap_orphan_expressions(self, tree , print_id: int):
        new_tree_body = []

        for node in tree.body:
            if isinstance(node, ast.Expr):
                new_expr = ast.Expr(
                    value=ast.Call(
                        func=ast.Name(id=print_id, ctx=ast.Load()),
                        args=[node.value],
                        keywords=[]
                    )
                )
                ast.fix_missing_locations(new_expr)
                new_tree_body.append(new_expr)
            else:
                new_tree_body.append(node)

        tree.body = new_tree_body
        return compile(tree, filename='<ast>', mode='exec')
    
    def run_code(self, code: str) -> Tuple[bool, Any]:
        captured_output = io.StringIO()

        def custom_print(*args, **kwargs):
            print(*args, **kwargs, file=captured_output)

        try:
            global_vars = {
                "__builtins__": {
                    **utility_builtins, **safe_builtins, **limited_builtins, **safe_builtins_2,
                    **{"__import__": __import__, "_print_": custom_print, "print": custom_print}
                },
            }
            
            tree = ast.parse(code, mode='exec')
            code_allowed, message_code = self.is_code_allowed(tree)
            if not code_allowed:
                return False, message_code
            
            exec(self.wrap_orphan_expressions(tree, "print"), global_vars)
                

            captured_string = captured_output.getvalue().strip()
            last_statement_is_print = isinstance(tree.body[-1], ast.Expr) and \
                            isinstance(tree.body[-1].value, ast.Call) and \
                            isinstance(tree.body[-1].value.func, ast.Name) and \
                            tree.body[-1].value.func.id == "print"
                            
            if last_statement_is_print:
                out = captured_string.rstrip("\nNone")
            else:
                out = f"{captured_string}\nNone" if captured_string else "None"
            return True, out

        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            traceback_details = traceback.format_exception(exc_type, exc_value, exc_traceback)
            formatted_traceback = ''.join(traceback_details)
            return False, formatted_traceback

    def evaluate(self, code: str) -> Tuple[bool, Any]:
        try:
            success, captured_output = self.run_code(code)
        except RuntimeError as e:
            return False, str(e)
        
        return success, captured_output

if __name__ == "__main__":
    execd=FinalStatefulSafeCodeEvaluator(["numpy", "scipy"])
    code = """
import scipy.integrate as spi;import numpy as np;f = lambda u: np.sin(u)/u;integral_value, error = spi.quad(f, 0, 1);print(integral_value)
"""
    print(execd.run_code(code)[1])
    print(execd.run_code("print(1)")[1])

