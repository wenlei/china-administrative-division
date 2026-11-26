import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import switch_backend as release


class SwitchBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'upstream.conf').write_text(release.upstream('blue'))
        self.blue = dict(status='ok',service='regionCheck',version='old',data_sha256='a'*64,current_count=10)
        self.green = dict(self.blue,version='new',data_sha256='b'*64)
        self.front = {'Id':'router-id','Image':'nginx-id','State':{'Status':'running'},
                      'NetworkSettings':{'Networks':{'isolated':{}}},
                      'Mounts':[{'Destination':'/etc/nginx/region-check','Source':str(self.root),'RW':False}]}
        self.back = dict(self.front,Id='green-id',Image='candidate-image')
        self.commands = []
        self.fail_reload = False
        self.reloads = 0
        def command(*args):
            self.commands.append(args)
            if 'reload' in args:
                self.reloads += 1
                if self.fail_reload and self.reloads==1:
                    raise RuntimeError('synthetic reload failure')
            return ''
        def health(client,host):
            if host=='router':host=release.read_backend((self.root/'upstream.conf').read_text())
            return copy.deepcopy(self.blue if host=='blue' else self.green)
        for name,value in [('run',command),('inspect',lambda n:self.front if n=='router' else self.back),('health',health)]:
            p=patch.object(release,name,side_effect=value);p.start();self.addCleanup(p.stop)

    def switch(self,execute=False,**kwargs):
        return release.switch(self.root,'router','green','new','b'*64,
                              kwargs.pop('image','candidate-image'),execute=execute,**kwargs)

    def test_plan_does_not_write_or_reload(self):
        result=self.switch()
        self.assertEqual(result['status'],'validated-not-switched')
        self.assertEqual(release.read_backend((self.root/'upstream.conf').read_text()),'blue')
        self.assertFalse(any('reload' in c for c in self.commands))

    def test_switch_keeps_router_and_both_backends(self):
        result=self.switch(True)
        self.assertEqual(result['router_container_id'],'router-id')
        self.assertEqual(result['containers_stopped'],0)
        self.assertTrue(result['old_backend_retained'])
        self.assertFalse(any(c[1] in ('stop','rm','restart','kill') for c in self.commands))

    def test_reload_failure_restores_old_configuration_and_route(self):
        self.fail_reload=True
        with self.assertRaisesRegex(RuntimeError,'reload failure'):self.switch(True)
        self.assertEqual(release.read_backend((self.root/'upstream.conf').read_text()),'blue')
        self.assertEqual(self.reloads,2)

    def test_bad_image_refused_before_mutation(self):
        with self.assertRaisesRegex(RuntimeError,'image'):self.switch(True,image='unknown-image')
        self.assertEqual(self.reloads,0)

    def test_unhealthy_or_wrong_data_refused(self):
        self.green['data_sha256']='c'*64
        with self.assertRaisesRegex(RuntimeError,'identity'):self.switch(True)
        self.assertEqual(self.reloads,0)

    def test_old_requests_block_reuse_of_inactive_slot(self):
        with patch.object(release,'draining_workers',return_value=True):
            with self.assertRaisesRegex(RuntimeError,'draining'):self.switch(True)
        self.assertEqual(self.reloads,0)

    def test_directory_mount_must_match(self):
        self.front['Mounts'][0]['Source']='/some-other-release'
        with self.assertRaisesRegex(RuntimeError,'config directory'):self.switch(True)

    def test_host_injection_and_unknown_config_refused(self):
        for value in ['blue;quit','blue/../../other','blue:80','blue\nserver other']:
            with self.assertRaises(ValueError):release.upstream(value)
        (self.root/'upstream.conf').write_text('upstream other { server unrelated:8000; }')
        with self.assertRaises(ValueError):self.switch(True)


if __name__=='__main__':unittest.main()
