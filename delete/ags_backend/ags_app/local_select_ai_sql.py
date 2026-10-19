"""Shared, offline Oracle SELECT allow-list, also checked before Oracle parses output."""
SCHEMA = 'AEGIS_LOCAL_AI'
TABLES = frozenset(('LOCAL_DATASETS', 'LOCAL_DOCUMENTS', 'LOCAL_EXTRACTIONS'))


def validate_sql(value):
    """Conservative Oracle AST allow-list; parsing alone never grants access."""
    import sqlglot
    from sqlglot import exp
    if not isinstance(value, str) or not value.strip() or len(value) > 16000:
        raise ValueError('The local model did not return a usable SQL query.')
    try:
        trees = sqlglot.parse(value, read='oracle')
    except (sqlglot.errors.SqlglotError, ValueError):
        raise ValueError('Generated SQL could not be validated. Nothing was executed.') from None
    allowed = {
        'Select', 'Column', 'Table', 'From', 'Identifier', 'Star', 'Alias', 'TableAlias',
        'Where', 'Group', 'Having', 'Order', 'Ordered', 'Limit', 'Fetch', 'LimitOptions', 'Offset',
        'Join', 'Distinct', 'Paren', 'Subquery', 'And', 'Or', 'Not', 'EQ', 'NEQ',
        'GT', 'GTE', 'LT', 'LTE', 'In', 'Between', 'Is', 'Null', 'Boolean', 'Literal',
        'Neg', 'Add', 'Sub', 'Mul', 'Div', 'Mod', 'Case', 'If',
        'Count', 'Sum', 'Min', 'Max', 'Avg', 'Round', 'Abs', 'Coalesce', 'Lower', 'Upper', 'Length', 'Trim', 'Nullif',
        'Like', 'ILike', 'DPipe',
    }
    if len(trees) != 1 or not isinstance(trees[0], exp.Select):
        raise ValueError('Only one read-only SELECT is permitted. Nothing was executed.')
    tree = trees[0]
    nodes = list(tree.walk())
    tables = list(tree.find_all(exp.Table))
    if (not tables or len(nodes) > 500 or len(tables) > 8
            or any(type(node).__name__ not in allowed for node in nodes)
            or any(node.comments for node in nodes)
            or any(select.args.get('locks') or select.args.get('into') for select in tree.find_all(exp.Select))):
        raise ValueError('Generated SQL uses unsupported operations. Nothing was executed.')
    for table in tables:
        if (not isinstance(table.this, exp.Identifier) or table.name.upper() not in TABLES
                or table.catalog or table.db and table.db.upper() != SCHEMA
                or set(table.args) - {'this', 'db', 'catalog', 'alias'}):
            raise ValueError('SQL may read only the three scoped metadata tables.')
    if any(len(column.parts) > 2 for column in tree.find_all(exp.Column)):
        raise ValueError('Qualified package or system expressions are not permitted.')
    # Render the validated AST, dropping unparsed text and Oracle terminators.
    return tree.sql(dialect='oracle')
