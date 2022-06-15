# skylark

#### Description
Skylark is a next-generation QoS-aware scheduler which provides coordinated resource scheduling for co-located applications with different QoS requirements. Typical applications are VM and Container. The architecture is highly scalable, so it's easy to be extended to support new types of applications and resources in the future.

#### Software Architecture

Totally consist of four components：
1.  data_collector (collect data)
2.  qos_analyzer (analysis QoS status)
3.  qos_controller (control QoS status)
4.  skylark.py (drive above components periodically)

#### Installation

1.  git clone <url>
2.  make && make install
3.  systemctl daemon-reload

#### Instructions

Startup
1.  systemctl start skylarkd

Modify parameters and restart
1.  vim /etc/sysconfig/skylarkd
2.  systemctl restart skylarkd

#### Contribution

1.  Fork the repository
2.  Create Feat_xxx branch
3.  Commit your code
4.  Create Pull Request
