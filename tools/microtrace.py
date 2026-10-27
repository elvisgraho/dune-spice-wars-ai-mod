"""Logging-only comparison of an army's previous and requested fight micro state.

Reads vanilla's per-fight map. It changes only the wrapper's emit flag; the
original changeArmyMicro call always runs. No extra per-army maps are allocated.
"""


def previous_micro(fb, args, emit, repeats=False):
    from aware import B

    b, cx = B(fb), fb.cx
    done = f'microcmp{len(fb.ops)}'
    previous = fb.reg(cx.t('dyn'))
    fb.op('Null', dst=previous)
    mapping = b.cast(fb.get(args[1], 'micro'), 'haxe.ds.ObjectMap')
    fb.op('JNull', reg=mapping, offset=done)
    old = b.call('haxe.ds.ObjectMap.get', mapping, fb.dyn(args[2]))
    fb.op('Mov', dst=previous, src=old)
    if not repeats:
        fb.op('JNull', reg=old, offset=done)
        fb.op('JNull', reg=args[3], offset=done)
        behavior_type = fb.regs[args[3]]
        typed_old = fb.reg(behavior_type)
        fb.op('SafeCast', dst=typed_old, src=old)
        old_kind, new_kind = fb.reg(cx.t('i32')), fb.reg(cx.t('i32'))
        fb.op('EnumIndex', dst=old_kind, value=typed_old)
        fb.op('EnumIndex', dst=new_kind, value=args[3])
        fb.op('JNotEq', a=old_kind, b=new_kind, offset=done)
        for index, constructor in enumerate(cx.code.types[behavior_type].definition.constructs):
            name = constructor.name.resolve(cx.code)
            if name not in ('Idle', 'Attack', 'Reposition', 'Flee'):
                continue  # unknown future behavior: keep the observation
            next_kind = f'{done}_{index}'
            fb.op('JNotEq', a=old_kind, b=b.const('i32', index), offset=next_kind)
            for field, typ in enumerate(constructor.params):
                before, after = fb.reg(typ.value), fb.reg(typ.value)
                fb.op('EnumField', dst=before, value=typed_old, construct=index, field=field)
                fb.op('EnumField', dst=after, value=args[3], construct=index, field=field)
                if field == 0 and name in ('Reposition', 'Flee'):
                    fb.op('JNull', reg=before, offset=done)
                    fb.op('JNull', reg=after, offset=done)
                    for coordinate in ('x', 'y'):
                        fb.op('JNotEq', a=b.field(before, coordinate), b=b.field(after, coordinate), offset=done)
                else:
                    fb.op('JNotEq', a=before, b=after, offset=done)
            fb.op('Bool', dst=emit, value=False)
            fb.op('JAlways', offset=done)
            fb.label(next_kind)
    fb.label(done)
    return previous
