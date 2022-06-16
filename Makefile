DIR := $(shell basename $(shell pwd))

all: skylarkd libskylarkmsr.so

skylarkd: *.py */*.py
	python3 -m zipapp ../$(DIR) --output=../skylarkd --main="skylark:main" --python="/usr/bin/env python3"
	mv ../skylarkd .

libskylarkmsr.so: data_collector/get_msr.c
	gcc --share -fPIC -g -o libskylarkmsr.so data_collector/get_msr.c

install: skylarkd libskylarkmsr.so skylarkd.service skylarkd.sysconfig low_prio_machine.slice high_prio_machine.slice
	install -T -D skylarkd $(DESTDIR)/usr/sbin/skylarkd
	install -T -D libskylarkmsr.so $(DESTDIR)/usr/lib/libskylarkmsr.so
	install -T -D -m 644 skylarkd.sysconfig $(DESTDIR)/etc/sysconfig/skylarkd
	install -T -D -m 644 skylarkd.service $(DESTDIR)/usr/lib/systemd/system/skylarkd.service
	install -T -D -m 644 low_prio_machine.slice $(DESTDIR)/etc/systemd/system/low_prio_machine.slice
	install -T -D -m 644 high_prio_machine.slice $(DESTDIR)/etc/systemd/system/high_prio_machine.slice

.PHONY: clean
clean:
	rm -f skylarkd
	rm -f *.so
