from setuptools import setup, find_packages

setup(
    name                = "skylark-sched",
    version             = "1.0.0",
    maintainer          = "Keqian Zhu",
    maintainer_email    = "zhukeqian1@huawei.com",
    description         = "Skylark is a next-generation QoS-aware scheduler",
    url                 = "https://gitee.com/openeuler/skylark",

    packages            = ['.'] + find_packages(),
    scripts             = ['skylark.py'],

    python_requires='>=3',
)
