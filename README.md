# skylark

#### 介绍
Skylark is a next-generation QoS-aware scheduler which provides coordinated resource scheduling for co-located applications with different QoS requirements. Typical applications are VM and Container. The architecture is highly scalable, so it's easy to be extended to support new types of applications and resources in the future.

#### 软件架构

总体分为四部分：
1.  data_collector（数据采集模块）
2.  qos_analyzer（QoS实时分析模块）
3.  qos_controller（QoS实时控制模块）
4.  skylark.py（周期性驱动以上三个模块）

#### 安装教程

1.  git clone 仓库url
2.  make && make install
3.  systemctl daemon-reload

#### 使用说明

启动
1.  systemctl start skylarkd

修改参数并重启
1.  vim /etc/sysconfig/skylarkd
2.  systemctl restart skylarkd

#### 参与贡献

1.  Fork 本仓库
2.  新建 Feat_xxx 分支
3.  提交代码
4.  新建 Pull Request
