all: skylarkd libskylarkmsr.so

skylarkd: *.py */*.py
	python3 setup.py sdist
	pip3 install pex
	pex -o skylarkd --disable-cache -r requirements.txt skylark-sched -f dist -c skylark.py

libskylarkmsr.so: data_collector/get_msr.c
	gcc --share -fPIC -o libskylarkmsr.so data_collector/get_msr.c

install: skylarkd libskylarkmsr.so skylarkd.service skylarkd.sysconfig low_prio_machine.slice high_prio_machine.slice
	install -T -D skylarkd $(DESTDIR)/usr/sbin/skylarkd
	install -T -D libskylarkmsr.so $(DESTDIR)/usr/lib/libskylarkmsr.so
	install -T -D -m 644 skylarkd.sysconfig $(DESTDIR)/etc/sysconfig/skylarkd
	install -T -D -m 644 skylarkd.service $(DESTDIR)/etc/systemd/system/skylarkd.service
	install -T -D -m 644 low_prio_machine.slice $(DESTDIR)/etc/systemd/system/low_prio_machine.slice
	install -T -D -m 644 high_prio_machine.slice $(DESTDIR)/etc/systemd/system/high_prio_machine.slice

.PHONY: clean
clean:
	rm -rf dist skylark_sched.egg-info
	rm -rf __pycache__ */__pycache__
	rm skylarkd
	rm *.so
