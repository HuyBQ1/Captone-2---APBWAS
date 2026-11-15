"""Restricted arithmetic for cached XLSX formulas; never eval/exec model code."""
import ast,math,operator,re
from decimal import Decimal,localcontext,ROUND_HALF_UP

def col_number(col):
    value=0
    for c in col:value=value*26+ord(c)-64
    return value

def cached_formulas(columns,rows,formulas):
    cells={f'{chr(65+c)}{r+2}':v for r,row in enumerate(rows) for c,v in enumerate(row)}
    expressions={f['cell']:f['expression'].lstrip('=').strip().upper() for f in formulas}
    if len(expressions)!=len(formulas):raise ValueError('Mỗi ô chỉ có một công thức.')
    def coordinate(cell):
        match=re.fullmatch(r'([A-T])([1-9]\d{0,3})',cell)
        if not match:raise ValueError('Địa chỉ ô không hợp lệ.')
        c,r=ord(match[1])-65,int(match[2])
        if r<2 or r>len(rows)+1 or c>=len(columns):raise ValueError('Công thức tham chiếu ngoài bảng dữ liệu.')
        return c,r
    for cell in expressions:coordinate(cell)
    cache={};visiting=set()
    def number(value):
        if isinstance(value,bool):return int(value)
        if not isinstance(value,(int,float)) or not math.isfinite(value) or abs(value)>1e100:raise ValueError('Ô tính toán phải là số hữu hạn trong giới hạn.')
        return value
    def cell_value(cell):
        coordinate(cell)
        if cell in cache:return cache[cell]
        if cell in visiting or len(visiting)>100:raise ValueError('Công thức bị vòng lặp hoặc quá sâu.')
        if cell not in expressions:return cells.get(cell)
        visiting.add(cell);expr=expressions[cell]
        if not re.fullmatch(r'[A-Z0-9_.,:+*/() \-]+',expr):raise ValueError('Công thức chỉ hỗ trợ số, ô cùng bảng, + - * / và SUM AVERAGE MIN MAX COUNT ROUND.')
        refs={}
        def replace(match):
            key=f'_R{len(refs)}';refs[key]=match[0];return key
        rewritten=re.sub(r'(?<![A-Z0-9_])[A-Z]{1,3}[1-9]\d{0,3}(?::[A-Z]{1,3}[1-9]\d{0,3})?(?![A-Z0-9_])',replace,expr)
        def reference(ref):
            if ':' not in ref:return cell_value(ref)
            a,b=ref.split(':');c1,r1=coordinate(a);c2,r2=coordinate(b)
            if c1>c2 or r1>r2:raise ValueError('Vùng tham chiếu bị đảo.')
            return [cell_value(f'{chr(65+c)}{r}') for r in range(r1,r2+1) for c in range(c1,c2+1)]
        def walk(node):
            if isinstance(node,ast.Constant) and isinstance(node.value,(int,float)):return number(node.value)
            if isinstance(node,ast.Name) and node.id in refs:return reference(refs[node.id])
            if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):return number(walk(node.operand))*(1 if isinstance(node.op,ast.UAdd) else -1)
            if isinstance(node,ast.BinOp) and type(node.op) in (ast.Add,ast.Sub,ast.Mult,ast.Div):
                left,right=number(walk(node.left)),number(walk(node.right))
                try:return number({ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv}[type(node.op)](left,right))
                except ZeroDivisionError:raise ValueError('Công thức chia cho 0; cần bổ sung dữ liệu hợp lệ.') from None
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and not node.keywords:
                args=[walk(a) for a in node.args];name=node.func.id
                if name=='ROUND' and len(args)==2 and isinstance(args[1],(int,float)) and int(args[1])==args[1] and -10<=args[1]<=10:
                    with localcontext() as context:
                        context.prec=128
                        return float(Decimal(str(number(args[0]))).quantize(Decimal(1).scaleb(-int(args[1])),rounding=ROUND_HALF_UP))
                if name not in ('SUM','AVERAGE','MIN','MAX','COUNT'):raise ValueError('Hàm Excel chưa được hỗ trợ.')
                values=[v for a in args for v in (a if isinstance(a,list) else [a]) if isinstance(v,(int,float)) and not isinstance(v,bool)]
                if name=='COUNT':return len(values)
                if name=='SUM':return sum(values)
                if not values:raise ValueError('Hàm cần ít nhất một số.')
                return sum(values)/len(values) if name=='AVERAGE' else min(values) if name=='MIN' else max(values)
            raise ValueError('Công thức không nằm trong phạm vi cho phép.')
        try:value=number(walk(ast.parse(rewritten,mode='eval').body))
        except (SyntaxError,RecursionError,OverflowError):raise ValueError('Công thức không hợp lệ hoặc vượt giới hạn.') from None
        visiting.remove(cell);cache[cell]=value;return value
    for cell in expressions:cell_value(cell)
    return {cell:{'formula':expressions[cell],'value':cache[cell]} for cell in expressions}
