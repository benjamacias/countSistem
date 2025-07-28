import ast
import sys
import keyword
import re
import os

class ComplejidadVisitor(ast.NodeVisitor):
    def __init__(self):
        self.max_nivel_bucle = 0
        self.nivel_actual_bucle = 0
        self.recursion = set()
        self.funciones = set()
        self.llamadas = []
        self.tiene_while_log = False
        self.tiene_for_log = False

    def visit_FunctionDef(self, node):
        self.funciones.add(node.name)
        self.nivel_actual_bucle = 0
        self.generic_visit(node)

    def visit_For(self, node):
        self.nivel_actual_bucle += 1
        if self.nivel_actual_bucle > self.max_nivel_bucle:
            self.max_nivel_bucle = self.nivel_actual_bucle
        # Nuevo: detectar O(log n) en for
        if self.is_log_for(node):
            self.tiene_for_log = True
        self.generic_visit(node)
        self.nivel_actual_bucle -= 1

    def visit_While(self, node):
        self.nivel_actual_bucle += 1
        if self.nivel_actual_bucle > self.max_nivel_bucle:
            self.max_nivel_bucle = self.nivel_actual_bucle
        if self.is_log_while(node):
            self.tiene_while_log = True
        self.generic_visit(node)
        self.nivel_actual_bucle -= 1

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            self.llamadas.append(node.func.id)
        self.generic_visit(node)

    def is_log_while(self, node):
        if isinstance(node.test, ast.Compare):
            left = node.test.left
            comparators = node.test.comparators
            if (isinstance(left, ast.Name) and len(comparators) == 1 and
                isinstance(comparators[0], ast.Constant) and comparators[0].value == 0):
                var = left.id
                for child in ast.walk(node):
                    if isinstance(child, ast.AugAssign):
                        if (isinstance(child.target, ast.Name) and child.target.id == var and
                            (isinstance(child.op, ast.FloorDiv) or isinstance(child.op, ast.RShift))):
                            return True
                    if isinstance(child, ast.Assign):
                        if (len(child.targets) == 1 and isinstance(child.targets[0], ast.Name) and
                            child.targets[0].id == var and
                            isinstance(child.value, ast.BinOp) and
                            (isinstance(child.value.op, ast.FloorDiv) or isinstance(child.value.op, ast.RShift))):
                            return True
        return False

    def is_log_for(self, node):
        """
        Detecta patrones O(log n) en for. Busca:
        - for i in ...: (donde en el cuerpo i se multiplica o divide por 2)
        - for i in range con step que es potencia de 2 (no común en Python)
        """
        # Solo casos básicos y realistas:
        if isinstance(node.target, ast.Name):
            var = node.target.id
            # Analiza si en el cuerpo hay i *= 2, i //= 2, i = i * 2, i = i // 2, etc.
            for child in ast.walk(node):
                if isinstance(child, ast.AugAssign):
                    if (isinstance(child.target, ast.Name) and child.target.id == var and
                        (isinstance(child.op, ast.Mult) or isinstance(child.op, ast.FloorDiv))):
                        return True
                if isinstance(child, ast.Assign):
                    if (len(child.targets) == 1 and isinstance(child.targets[0], ast.Name) and
                        child.targets[0].id == var and
                        isinstance(child.value, ast.BinOp) and
                        (isinstance(child.value.op, ast.Mult) or isinstance(child.value.op, ast.FloorDiv))):
                        return True
        return False

    def report(self):
        recursiva = any(f in self.llamadas for f in self.funciones)
        if recursiva:
            self.recursion = set(f for f in self.funciones if f in self.llamadas)

        print(f"\nNivel máximo de bucles anidados: {self.max_nivel_bucle}")
        if self.recursion:
            print(f"¡Recursión detectada en: {', '.join(self.recursion)}!")
        # EXPLICACIÓN
        if self.recursion:
            print("Complejidad probable: Exponencial o peor (¡recursión!)")
            print("→ Se detectó recursión: las funciones se llaman a sí mismas. Esto suele dar O(2^n), O(n!), etc. si no hay memoización.")
        elif self.tiene_while_log or self.tiene_for_log:
            print("Complejidad probable: O(log n)")
            if self.tiene_while_log:
                print("→ Se detectó un bucle 'while' que divide la variable por 2 (o le hace shift a la derecha) en cada iteración.")
                print("→ Ejemplo típico: while n > 0: n //= 2. Este patrón es O(log n).")
            if self.tiene_for_log:
                print("→ Se detectó un bucle 'for' donde la variable se multiplica o divide por 2 en cada iteración.")
                print("→ Ejemplo típico: for i in ...: i *= 2. Este patrón es O(log n).")
        elif self.max_nivel_bucle == 0:
            print("Complejidad probable: O(1) o O(n) (sin bucles anidados)")
            print("→ No se detectaron bucles anidados ni recursión. Probablemente el algoritmo es directo o lineal.")
        elif self.max_nivel_bucle == 1:
            print("Complejidad probable: O(n)")
            print("→ Se encontró un bucle de un solo nivel (for o while). Normalmente esto indica O(n).")
        elif self.max_nivel_bucle == 2:
            print("Complejidad probable: O(n^2)")
            print("→ Se encontraron dos bucles anidados (for/while dentro de otro for/while). Normalmente esto es O(n²).")
        else:
            print(f"Complejidad probable: O(n^{self.max_nivel_bucle})")
            print(f"→ Se encontraron {self.max_nivel_bucle} bucles anidados. Esto suele ser O(n^{self.max_nivel_bucle}).")

class ChequeosExtra(ast.NodeVisitor):
    def __init__(self):
        self.nombres_invalidos = set()
        self.nombres = set()
        self.nombres_funcion = set()
        self.nombres_clase = set()
        self.reservadas = set(keyword.kwlist)
        self.regex_valido = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")  # Identificador Python válido

    def visit_Name(self, node):
        self.nombres.add(node.id)
        if not self.regex_valido.match(node.id) or node.id in self.reservadas:
            self.nombres_invalidos.add(node.id)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self.nombres_funcion.add(node.name)
        if not self.regex_valido.match(node.name) or node.name in self.reservadas:
            self.nombres_invalidos.add(node.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        self.nombres_clase.add(node.name)
        if not self.regex_valido.match(node.name) or node.name in self.reservadas:
            self.nombres_invalidos.add(node.name)
        self.generic_visit(node)

    def visit_arg(self, node):
        if not self.regex_valido.match(node.arg) or node.arg in self.reservadas:
            self.nombres_invalidos.add(node.arg)
        self.generic_visit(node)

class ChequeosModulos(ast.NodeVisitor):
    def __init__(self, prohibidos=None):
        self.prohibidos = set(prohibidos) if prohibidos else {"os", "sys", "subprocess"}
        self.importados_prohibidos = set()

    def visit_Import(self, node):
        for alias in node.names:
            if alias.name.split('.')[0] in self.prohibidos:
                self.importados_prohibidos.add(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        if node.module and node.module.split('.')[0] in self.prohibidos:
            self.importados_prohibidos.add(node.module)
        self.generic_visit(node)

def analizar_archivo(path):
    print(f"\nAnalizando archivo: {path}")
    if not os.path.isfile(path):
        print(f"Error: El archivo '{path}' no existe.")
        return

    with open(path, 'r', encoding='utf-8') as f:
        codigo = f.read()

    try:
        tree = ast.parse(codigo)
    except SyntaxError as e:
        print("¡Error de sintaxis detectado!")
        print(f"Tipo de error: {e.msg}")
        print(f"Línea: {e.lineno}, Columna: {e.offset}")
        print(f"Texto problemático: {e.text.strip() if e.text else ''}")
        return

    nombres_checker = ChequeosExtra()
    nombres_checker.visit(tree)
    if nombres_checker.nombres_invalidos:
        print("\n¡Atención! Nombres de variables o funciones inválidos encontrados:")
        for n in nombres_checker.nombres_invalidos:
            print("   -", n)
    
    modulos_checker = ChequeosModulos(prohibidos={"os", "subprocess", "sys"})
    modulos_checker.visit(tree)
    if modulos_checker.importados_prohibidos:
        print("\n¡Atención! Se usaron módulos prohibidos:")
        for m in modulos_checker.importados_prohibidos:
            print("   -", m)
    
    visitor = ComplejidadVisitor()
    visitor.visit(tree)
    visitor.report()

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Uso: python complex.py archivo_a_analizar.py")
        sys.exit(1)
    archivo = sys.argv[1]
    analizar_archivo(archivo)
