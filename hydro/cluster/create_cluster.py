#!/usr/bin/env python3

#  Copyright 2019 U.C. Berkeley RISE Lab
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#  Modifications copyright (C) 2021 Taras Lykhenko, Rafael Soares

import argparse
import os

import yaml

from hydro.cluster.add_nodes import batch_add_nodes
from hydro.shared import util

BATCH_SIZE = 100


def create_cluster(mem_count, ebs_count, func_count, gpu_count, sched_count,
                   route_count, bench_count, local, cfile, ssh_key):

    if 'HYDRO_HOME' not in os.environ:
        raise ValueError('HYDRO_HOME environment variable must be set to be '
                         + 'the directory where all Hydro project repos are '
                         + 'located.')
    prefix = os.path.join(os.environ['HYDRO_HOME'], 'cluster/hydro/cluster')

    client, apps_client = util.init_k8s()

    print('Creating management pods...')
    management_spec = util.load_yaml('yaml/pods/management-pod.yml', prefix)

    print('Creating management pods...')
    print(util.NAMESPACE)
    print('Creating management pods...')
    print(management_spec)

    client.create_namespaced_pod(namespace=util.NAMESPACE, body=management_spec)
    print('Creating management pods...')


    # Waits until the management pod starts to move forward -- we need to do
    # this because other pods depend on knowing the management pod's IP address.
    management_ip = util.get_pod_ips(client, 'role=management', is_running=True)[0]


    # Copy kube config file to management pod, so it can execute kubectl
    # commands, in addition to SSH keys and KVS config.
    management_podname = management_spec['metadata']['name']
    kcname = management_spec['spec']['containers'][0]['name']

    os.system('cp %s anna-config.yml' % cfile)

    kubecfg = os.path.join(os.environ['HOME'], '.kube/config')
    os.system('cp %s %s' % (kubecfg,  os.environ['HOME']))

    kube_config_copy = util.load_yaml('config', os.environ['HOME'])
    kubecfg = os.path.join(os.environ['HOME'], 'config')

    if local:
        cert_aut = kube_config_copy['clusters'][0]['cluster']['certificate-authority']
        cert = kube_config_copy['users'][0]['user']['client-certificate']
        key = kube_config_copy['users'][0]['user']['client-key']
        util.copy_file_to_pod(client, cert_aut, management_podname, '/root/.kube/',
                              kcname)
        util.copy_file_to_pod(client, cert, management_podname, '/root/.kube/',
                              kcname)
        util.copy_file_to_pod(client, key, management_podname, '/root/.kube/',
                              kcname)

        kube_config_copy['clusters'][0]['cluster']['certificate-authority'] = os.path.join('/root/.kube/',os.path.basename(cert_aut))
        kube_config_copy['users'][0]['user']['client-certificate'] = os.path.join('/root/.kube/',os.path.basename(cert))
        kube_config_copy['users'][0]['user']['client-key'] = os.path.join('/root/.kube/',os.path.basename(key))

        with open(kubecfg, 'w') as file:
            yaml.dump(kube_config_copy, file)

    util.copy_file_to_pod(client, kubecfg, management_podname, '/root/.kube/',
                          kcname)
    pods = client.list_namespaced_pod(namespace=util.NAMESPACE).items


    util.copy_file_to_pod(client, 'anna-config.yml', management_podname,
                          '/hydro/anna/conf/', kcname)

    print("# Start the monitoring pod.")
    mon_spec = util.load_yaml('yaml/pods/monitoring-pod.yml', prefix)
    util.replace_yaml_val(mon_spec['spec']['containers'][0]['env'], 'MGMT_IP',
                          management_ip)
    client.create_namespaced_pod(namespace=util.NAMESPACE, body=mon_spec)

    print('wait')
    # Wait until the monitoring pod is finished creating to get its IP address
    # and then copy KVS config into the monitoring pod.
    util.get_pod_ips(client, 'role=monitoring')
    util.copy_file_to_pod(client, 'anna-config.yml',
                          mon_spec['metadata']['name'],
                          '/hydro/anna/conf/',
                          mon_spec['spec']['containers'][0]['name'])
    os.system('rm anna-config.yml')

    print('Creating %d routing nodes...' % (route_count))
    batch_add_nodes(client, apps_client, cfile, ['routing'], [route_count], BATCH_SIZE, prefix)
    util.get_pod_ips(client, 'role=routing')

    print('Creating %d memory, %d ebs node(s)...' %
          (mem_count, ebs_count))
    batch_add_nodes(client, apps_client, cfile, ['memory', 'ebs'], [mem_count, ebs_count],BATCH_SIZE, prefix)

    print('Creating routing service...')
    service_spec = util.load_yaml('yaml/services/routing.yml', prefix)
    # Only create the routing service if it isn't up already
    # (e.g. from a previous execution of the script).
    if util.get_service_address(client, 'routing-service') is None:
        client.create_namespaced_service(namespace=util.NAMESPACE,
                                         body=service_spec)


    print('Adding %d scheduler nodes...' % (sched_count))
    batch_add_nodes(client, apps_client, cfile, ['scheduler'], [sched_count],
                    BATCH_SIZE, prefix)
    util.get_pod_ips(client, 'role=scheduler')

    print('Adding %d function, %d GPU nodes...' % (func_count, gpu_count))
    batch_add_nodes(client, apps_client, cfile, ['function', 'gpu'],
                        [func_count, gpu_count], BATCH_SIZE, prefix)

    print('Creating function service...')
    service_spec = util.load_yaml('yaml/services/function.yml', prefix)
    if util.get_service_address(client, 'function-service') is None:
        client.create_namespaced_service(namespace=util.NAMESPACE,
                                         body=service_spec)

    print('Adding %d benchmark nodes...' % (bench_count))
    batch_add_nodes(client, apps_client, cfile, ['benchmark'], [bench_count],
                    BATCH_SIZE, prefix)

    print('Finished creating all pods...')
    os.system('touch setup_complete')
    util.copy_file_to_pod(client, 'setup_complete', management_podname, '/hydro',
                          kcname)
    os.system('rm setup_complete')

    pods = client.list_namespaced_pod(namespace=util.NAMESPACE).items



    routing_svc_addr = util.get_service_address(client, 'routing-service')
    function_svc_addr = util.get_service_address(client, 'function-service')
    print('The routing service can be accessed here: \n\t%s' %
          (routing_svc_addr))
    print('The function service can be accessed here: \n\t%s' %
          (function_svc_addr))

def str2bool(v):
    if isinstance(v, bool):
       return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='''Creates a Hydro cluster
                                     using Kubernetes and kops. If no SSH key
                                     is specified, we use the default SSH key
                                     (~/.ssh/id_rsa), and we expect that the
                                     correponding public key has the same path
                                     and ends in .pub.

                                     If no configuration file base is
                                     specified, we use the default
                                     ($HYDRO_HOME/anna/conf/anna-base.yml).''')

    parser.add_argument('-m', '--memory', nargs=1, type=int, metavar='M',
                        help='The number of memory nodes to start with ' +
                        '(required)', dest='memory', required=True)
    parser.add_argument('-r', '--routing', nargs=1, type=int, metavar='R',
                        help='The number of routing  nodes in the cluster ' +
                        '(required)', dest='routing', required=True)
    parser.add_argument('-f', '--function', nargs=1, type=int, metavar='F',
                        help='The number of function nodes to start with ' +
                        '(required)', dest='function', required=True)
    parser.add_argument('-s', '--scheduler', nargs=1, type=int, metavar='S',
                        help='The number of scheduler nodes to start with ' +
                        '(required)', dest='scheduler', required=True)
    parser.add_argument('-g', '--gpu', nargs='?', type=int, metavar='G',
                        help='The number of GPU nodes to start with ' +
                        '(optional)', dest='gpu', default=0)
    parser.add_argument('-e', '--ebs', nargs='?', type=int, metavar='E',
                        help='The number of EBS nodes to start with ' +
                        '(optional)', dest='ebs', default=0)
    parser.add_argument('-b', '--benchmark', nargs='?', type=int, metavar='B',
                        help='The number of benchmark nodes in the cluster ' +
                        '(optional)', dest='benchmark', default=0)
    parser.add_argument('-l', '--local', nargs='?', type=str2bool, metavar='L',
                        help='Minikube cluster ' +
                             '(optional)', dest='local', default=False)
    parser.add_argument('--conf', nargs='?', type=str,
                        help='The configuration file to start the cluster with'
                        + ' (optional)', dest='conf',
                        default=os.path.join(os.getenv('HYDRO_HOME', '..'),
                                             'anna/conf/anna-base.yml'))
    parser.add_argument('--ssh-key', nargs='?', type=str,
                        help='The SSH key used to configure and connect to ' +
                        'each node (optional)', dest='sshkey',
                        default=os.path.join(os.environ['HOME'],
                                             '.ssh/id_rsa'))



    args = parser.parse_args()

    print(args.local)
    create_cluster(args.memory[0], args.ebs, args.function[0], args.gpu,
                   args.scheduler[0], args.routing[0], args.benchmark, args.local,
                   args.conf, args.sshkey)
