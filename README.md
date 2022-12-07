# skylark

#### 介绍
Skylark 是新一代 QoS 感知的资源调度器，可为不同 QoS 要求的混部业务提供合适的资源调度。典型的业务包含虚拟机和容器。本组件具有丰富的可扩展性，因此易于支持未来可能出现的新型业务和资源。

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
