# Copyright 2017 Intel Corporation
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ------------------------------------------------------------------------------

import unittest
import logging
import json
import subprocess
import shlex
import urllib.request
import urllib.error
import base64
import hashlib
import random

import cbor

from sawtooth_signing import create_context
from sawtooth_signing import CryptoFactory

from sawtooth_validator.journal.block_info_injector \
    import CONFIG_ADDRESS
from sawtooth_validator.journal.block_info_injector \
    import create_block_address
from sawtooth_validator.protobuf import block_info_pb2
from sawtooth_validator.protobuf.transaction_pb2 import Transaction
from sawtooth_validator.protobuf.transaction_pb2 import TransactionHeader

from sawtooth_validator.protobuf.batch_pb2 import Batch
from sawtooth_validator.protobuf.batch_pb2 import BatchList
from sawtooth_validator.protobuf.batch_pb2 import BatchHeader

from sawtooth_integration.tests.integration_tools import wait_for_rest_apis

LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

WAIT = 300
XO_PREFIX = '5b7349'
INTKEY_ADDRESS_PREFIX = hashlib.sha512(
    'intkey'.encode('utf-8')).hexdigest()[0:6]


def make_intkey_address(name):
    return INTKEY_ADDRESS_PREFIX + hashlib.sha512(
        name.encode('utf-8')).hexdigest()[-64:]


def get_blocks():
    response = query_rest_api('/blocks')
    return response['data']


def get_block_info_config():
    bic = block_info_pb2.BlockInfoConfig()
    bic.ParseFromString(get_state(CONFIG_ADDRESS))
    return bic


def get_block_info(block_num):
    bi = block_info_pb2.BlockInfo()
    bi.ParseFromString(get_state(create_block_address(block_num)))
    return bi


def get_state(address):
    response = query_rest_api('/state/%s' % address)
    return base64.b64decode(response['data'])


def get_state_by_prefix(prefix):
    response = query_rest_api('/state?address=' + prefix)
    return response['data']


def get_xo_state():
    state = get_state_by_prefix(XO_PREFIX)
    return state


def post_batch(batch):
    headers = {'Content-Type': 'application/octet-stream'}
    response = query_rest_api(
        '/batches', data=batch, headers=headers)
    response = submit_request('{}&wait={}'.format(response['link'], WAIT))
    return response


def query_rest_api(suffix='', data=None, headers=None):
    if headers is None:
        headers = {}
    url = 'http://rest-api:8008' + suffix
    return submit_request(urllib.request.Request(url, data, headers))


def submit_request(request):
    response = urllib.request.urlopen(request).read().decode('utf-8')
    return json.loads(response)


def send_xo_cmd(cmd_str):
    LOGGER.info('Sending xo cmd: %s', cmd_str)
    subprocess.run(
        shlex.split(cmd_str),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True)


def make_batches(signer, keys):
    return [create_batch(signer, [('set', k, 0)]) for k in keys]


def create_batch(signer, triples):
    transactions = [
        create_transaction(signer, verb, name, value)
        for verb, name, value in triples
    ]

    txn_signatures = [txn.header_signature for txn in transactions]

    header = BatchHeader(
        signer_public_key=signer.get_public_key().as_hex(),
        transaction_ids=txn_signatures
    ).SerializeToString()

    signature = signer.sign(header)

    batch = Batch(
        header=header,
        transactions=transactions,
        header_signature=signature)

    batch_list = BatchList(batches=[batch])

    return batch_list.SerializeToString()


def create_transaction(signer, verb, name, value):
    payload = cbor.dumps({'Verb': verb, 'Name': name, 'Value': value},
                         sort_keys=True)

    addresses = [make_intkey_address(name)]

    nonce = hex(random.randint(0, 2**64))

    txn_pub_key = signer.get_public_key().as_hex()
    header = TransactionHeader(
        signer_public_key=txn_pub_key,
        family_name="intkey",
        family_version="1.0",
        inputs=addresses,
        outputs=addresses,
        dependencies=[],
        payload_sha512=hashlib.sha512(payload).hexdigest(),
        batcher_public_key=signer.get_public_key().as_hex(),
        nonce=nonce
    )

    signature = signer.sign(header.SerializeToString())

    return Transaction(
        header=header.SerializeToString(),
        payload=payload,
        header_signature=signature)


class TestNamespaceRestriction(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        wait_for_rest_apis(['rest-api:8008'])

    def test_namespace_restriction(self):
        """
        Tests that namespaces stored on-chain are enforced by the
        validators. According to the sawtooth_settings declared in the docker
        compose file, the transaciton families are expected to behave
        as follows:
        - block_info transactions are allowed
        - intkey transactions are banned
        - xo transactions are allowed
        """
        context = create_context('secp256k1')
        signer = CryptoFactory(context).new_signer(
            context.new_random_private_key())

        batches = make_batches(signer, 'abcde')

        send_xo_cmd('sawtooth keygen')

        xo_cmds = [
            'xo create game',
            'xo take game 5',
            'xo take game 9',
            'xo create game2',
            'xo take game2 4',
        ]

        # Assert all block info transactions are committed
        for i, batch in enumerate(batches):
            post_batch(batch)
            send_xo_cmd('{} --url {} --wait {}'.format(
                xo_cmds[i],
                'http://rest-api:8008',
                WAIT))
            block_info = get_block_info(i)
            self.assertEqual(block_info.block_num, i)

        # Assert block info batches are first in the block and
        # that any other batch is of the xo family
        for block in get_blocks()[:-1]:
            LOGGER.debug(block['header']['block_num'])
            family_name = \
                block['batches'][0]['transactions'][0]['header']['family_name']
            self.assertEqual(family_name, 'block_info')
            for batch in block['batches'][1:]:
                self.assertEqual(
                    batch['transactions'][0]['header']['family_name'], 'xo')
