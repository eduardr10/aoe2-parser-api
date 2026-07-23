from mgz.summary import Summary
import io

filepath = r'C:\Users\Eduard Espinoza\Herd\api-parser\AgeIIDE_Replay_493183597.aoe2record'
with open(filepath, 'rb') as f:
    data = f.read()

s = Summary(io.BytesIO(data))
players = s.get_players()
for p in players:
    if p['number'] > 0:
        print('Jugador: %s (Civ: %d)' % (p['name'], p['civilization']))
print('Mapa: %s' % s.get_map().get('name'))
print('Duracion ms: %s' % s.get_duration())
print('Completada: %s' % s.get_completed())
print()
print('TODO OK - el parche funciona!')
