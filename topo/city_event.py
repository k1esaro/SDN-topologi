#!/usr/bin/env python3
"""Топология стенда «SDN-управление сетью при массовых мероприятиях».

Домен 1 (ONOS, порт 6653) — городская сеть оператора: ядро s1,s2 → агрегация s3,s4 →
доступ s5,s6. Домен 2 (Faucet, порт 6654) — сеть места проведения: пограничный s7 →
зоны доступа s8,s9,s10. Домены соединяет один линк s6 ↔ s7 — будущее узкое место.

Сейчас реализован только домен 1 (вечер 4 по START.md). Домен 2 и стык — см. TODO ниже.

Запуск:   sudo python3 topo/city_event.py
Очистка:  sudo mn -c        (перед каждым новым запуском, пока не привыкли)
"""

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info

# Оба контроллера в контейнерах на этой же машине, порты опубликованы наружу
# (см. compose/docker-compose.yml). Mininet ходит к ним по IP, не по DNS-имени.
ONOS_IP, ONOS_PORT = '127.0.0.1', 6653
FAUCET_IP, FAUCET_PORT = '127.0.0.1', 6654

# Оба домена в одной L2-подсети: на этапе 1 нужна связность через стык любым способом,
# маршрутизация между доменами только запутала бы диагностику (см. START.md, критерий 5).
SUBNET = '10.0.0.0/24'


def dpid(n):
    """0x7 -> '0000000000000007'. dpid обязан совпасть с dp_id в compose/faucet/faucet.yaml."""
    return format(n, '016x')


def build_domain1(net, c1):
    """Домен 1: городская сеть оператора, контроллер ONOS.

    Схема портов (задаётся явно через port1=/port2=, автонумерации не доверяем —
    на неё завязан compose/faucet/faucet.yaml в домене 2 и отладка dump-flows здесь):

      s1 ядро:        1→s2   2→s3   3→s4
      s2 ядро:        1→s1   2→s3   3→s4
      s3 агрегация:   1→s1   2→s2   3→s5   4→s6
      s4 агрегация:   1→s1   2→s2   3→s5   4→s6
      s5 доступ:      1→s3   2→s4   3→h_emg  4→h_va
      s6 доступ:      1→s3   2→s4   3→h_tms  4→СТЫК с доменом 2 (s7 порт 1)

    Агрегация подключена к обоим ядрам, доступ — к обеим агрегациям: альтернативные
    пути нужны на этапе 4, когда критичный трафик придётся уводить с перегруженного.
    Петли здесь не страшны: ONOS строит топологию по LLDP и сам считает дерево
    для broadcast — это не обучающийся L2-коммутатор.
    """
    info('*** Домен 1: коммутаторы\n')
    s1 = net.addSwitch('s1', dpid=dpid(0x1), protocols='OpenFlow13')   # ядро
    s2 = net.addSwitch('s2', dpid=dpid(0x2), protocols='OpenFlow13')   # ядро
    s3 = net.addSwitch('s3', dpid=dpid(0x3), protocols='OpenFlow13')   # агрегация
    s4 = net.addSwitch('s4', dpid=dpid(0x4), protocols='OpenFlow13')   # агрегация
    s5 = net.addSwitch('s5', dpid=dpid(0x5), protocols='OpenFlow13')   # доступ
    s6 = net.addSwitch('s6', dpid=dpid(0x6), protocols='OpenFlow13')   # доступ + стык

    info('*** Домен 1: хосты (таблица сервисов — PLAN.md, этап 2)\n')
    # MAC заданы явно: в dump-flows и в ONOS GUI хост сразу узнаётся по адресу.
    h_emg = net.addHost('h_emg', ip='10.0.0.11/24', mac='00:00:00:00:00:11')  # пульт экстренных служб
    h_va = net.addHost('h_va', ip='10.0.0.12/24', mac='00:00:00:00:00:12')    # сервер видеоаналитики
    h_tms = net.addHost('h_tms', ip='10.0.0.13/24', mac='00:00:00:00:00:13')  # управление транспортом

    info('*** Домен 1: линки\n')
    net.addLink(s1, s2, port1=1, port2=1)          # ядро ↔ ядро
    net.addLink(s1, s3, port1=2, port2=1)
    net.addLink(s2, s3, port1=2, port2=2)
    net.addLink(s1, s4, port1=3, port2=1)
    net.addLink(s2, s4, port1=3, port2=2)
    net.addLink(s3, s5, port1=3, port2=1)
    net.addLink(s4, s5, port1=3, port2=2)
    net.addLink(s3, s6, port1=4, port2=1)
    net.addLink(s4, s6, port1=4, port2=2)

    net.addLink(h_emg, s5, port1=0, port2=3)
    net.addLink(h_va, s5, port1=0, port2=4)
    net.addLink(h_tms, s6, port1=0, port2=3)

    return [s1, s2, s3, s4, s5, s6]


def build_domain2(net, c2):
    """Домен 2: сеть места проведения, контроллер Faucet. TODO — ваша часть.

    Схема портов уже зафиксирована в compose/faucet/faucet.yaml, менять её нельзя,
    иначе Faucet будет слать правила не в те порты:
      s7  dp_id 0x7  пограничный:  1→СТЫК с s6   2→s8   3→s9   4→s10
      s8  dp_id 0x8  видеонаблюдение: 1→s7   2→h_cam
      s9  dp_id 0x9  участники:       1→s7   2→h_ap1   3→h_ap2   4→h_ap3
      s10 dp_id 0xa  службы на месте: 1→s7   2→h_term

    Что нужно написать, по образцу build_domain1:
      1. Четыре addSwitch с dpid=dpid(0x7)...dpid(0xa) и protocols='OpenFlow13'.
         Внимание: s10 — это 0xa, а не 0x10.
      2. Хосты той же подсети 10.0.0.0/24:
         h_cam 10.0.0.21, h_ap1..h_ap3 10.0.0.31..33, h_term 10.0.0.41 (MAC — по образцу).
      3. Линки строго по таблице выше, с явными port1=/port2=.
      4. Вернуть список коммутаторов — он уйдёт в sw.start([c2]).

    Проверка, что попали в схему: после запуска в faucet.log должны появиться
    4 подключившихся DP без строк вида "unknown port" / "port X not configured".
    """
    s7 = net.addSwitch('s7', dpid=dpid(0x7), protocols = 'OpenFlow13')
    s8 = net.addSwitch('s8', dpid=dpid(0x8), protocols = 'OpenFlow13')
    s9 = net.addSwitch('s9', dpid=dpid(0x9), protocols = 'OpenFlow13')
    s10 = net.addSwitch('s10', dpid=dpid(0xa), protocols = 'OpenFlow13')

    h_cam = net.addHost('h_cam', ip='10.0.0.21/24', mac='00:00:00:00:00:21')  
    h_ap1 = net.addHost('h_ap1', ip='10.0.0.31/24', mac='00:00:00:00:00:31')
    h_ap2 = net.addHost('h_ap2', ip='10.0.0.32/24', mac='00:00:00:00:00:32')
    h_ap3 = net.addHost('h_ap3', ip='10.0.0.33/24', mac='00:00:00:00:00:33')    
    h_term = net.addHost('h_term', ip='10.0.0.41/24', mac='00:00:00:00:00:41')

    net.addLink(s7,s8, port1=2, port2=1 )
    net.addLink(s7,s9, port1=3, port2=1 )
    net.addLink(s7,s10, port1=4, port2=1 )

    net.addLink(h_cam,s8, port1=0, port2=2 )
    net.addLink(h_ap1,s9, port1=0, port2=2 )
    net.addLink(h_ap2,s9, port1=0, port2=3 )
    net.addLink(h_ap3,s9, port1=0, port2=4 )
    net.addLink(h_term,s10, port1=0, port2=2 )

    return (s7, s8, s9, s10)



def build_uplink(net, s6, s7):
    """Стык доменов: единственный линк s6(порт 4) ↔ s7(порт 1).

    Полосу (bw=) здесь пока НЕ ставим: узкое место появится на этапе 2, сейчас оно
    только помешает понять, почему не ходит пинг. На этапе 2 станет:
    net.addLink(s6, s7, port1=4, port2=1, cls=TCLink, bw=10)
    """
    net.addLink(s6, s7, port1=4, port2=1)


def run(with_domain2=False):
    # TCLink нужен только когда появится bw= на стыке; сейчас линки без ограничений.
    net = Mininet(controller=None, switch=OVSSwitch, link=TCLink, autoSetMacs=False,
                  build=False, waitConnected=False)

    info('*** Контроллеры\n')
    c1 = net.addController('c1', controller=RemoteController, ip=ONOS_IP, port=ONOS_PORT)
    c2 = net.addController('c2', controller=RemoteController, ip=FAUCET_IP, port=FAUCET_PORT)

    domain1 = build_domain1(net, c1)
    domain2 = build_domain2(net, c2) if with_domain2 else []
    if with_domain2:
        build_uplink(net, domain1[5], domain2[0])

    info('*** Сборка\n')
    net.build()
    c1.start()
    c2.start()

    # Ключевой момент: привязываем каждый коммутатор к СВОЕМУ контроллеру вручную.
    # net.start() привязал бы все ко всем — тогда домены перестали бы быть независимыми,
    # а вся работа строится на том, что это две раздельные зоны управления.
    info('*** Привязка коммутаторов к контроллерам\n')
    for sw in domain1:
        sw.start([c1])
    for sw in domain2:
        sw.start([c2])

    info('*** Готово. Проверки:\n'
         '    ONOS:   ssh -p 8101 karaf@localhost  ->  devices / links / hosts\n'
         '    ONOS:   curl -u onos:rocks http://localhost:8181/onos/v1/devices\n'
         '    Faucet: docker compose -f compose/docker-compose.yml logs faucet\n'
         '    Здесь:  pingall, dump, net, sh ovs-ofctl -O OpenFlow13 dump-flows s5\n'
         '    ONOS поднимает fwd не мгновенно: если первый pingall с потерями — повторите.\n')
    CLI(net)
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    # Домен 2 включится, когда будут дописаны build_domain2() и build_uplink().
    run(with_domain2=True)
