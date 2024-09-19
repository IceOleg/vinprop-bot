# -*- coding: utf-8 -*- #
# Copyright 2024 Google LLC. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Exports data from an AlloyDB cluster to Google Cloud Storage."""

from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals

from googlecloudsdk.api_lib.alloydb import api_util
from googlecloudsdk.api_lib.alloydb import cluster_operations
from googlecloudsdk.calliope import base
from googlecloudsdk.command_lib.alloydb import cluster_helper
from googlecloudsdk.command_lib.alloydb import flags
from googlecloudsdk.core import log
from googlecloudsdk.core import properties
from googlecloudsdk.core import resources


# TODO: b/312466999 - Change @base.DefaultUniverseOnly to
# @base.UniverseCompatible once b/312466999 is fixed.
# See go/gcloud-cli-running-tpc-tests.
@base.DefaultUniverseOnly
@base.ReleaseTracks(base.ReleaseTrack.ALPHA)
@base.Hidden
class Export(base.SilentCommand):
  """Export an AlloyDB cluster to Google Cloud Storage."""

  detailed_help = {
      'DESCRIPTION':
          '{description}',
      'EXAMPLES':
          """\
        To export a cluster, run:

          $ {command} my-cluster --region=us-central1 --database=my-database --gcs-uri=gs://my-bucket/my-export-file-path --select-query="SELECT * FROM my-table"
        """,
  }

  @staticmethod
  def Args(parser):
    """Specifies additional command flags.

    Args:
      parser: argparse.Parser: Parser object for command line inputs.
    """
    base.ASYNC_FLAG.AddToParser(parser)
    flags.AddRegion(parser)
    flags.AddCluster(parser)
    flags.AddDatabase(parser)
    flags.AddDestinationURI(parser)
    flags.AddExportOptions(parser)

  def ConstructExportRequestFromArgs(
      self, alloydb_messages, cluster_ref, args
  ):
    return cluster_helper.ConstructExportRequestFromArgsAlpha(
        alloydb_messages, cluster_ref, args
    )

  def Run(self, args):
    """Constructs and sends request.

    Args:
      args: argparse.Namespace, An object that contains the values for the
        arguments specified in the .Args() method.

    Returns:
      ProcessHttpResponse of the request made.
    """

    client = api_util.AlloyDBClient(self.ReleaseTrack())
    alloydb_client = client.alloydb_client
    alloydb_messages = client.alloydb_messages
    cluster_ref = client.resource_parser.Create(
        'alloydb.projects.locations.clusters',
        projectsId=properties.VALUES.core.project.GetOrFail,
        locationsId=args.region,
        clustersId=args.cluster)
    req = self.ConstructExportRequestFromArgs(
        alloydb_messages, cluster_ref, args
    )
    op = alloydb_client.projects_locations_clusters.Export(req)
    op_ref = resources.REGISTRY.ParseRelativeName(
        op.name, collection='alloydb.projects.locations.operations')
    if not args.async_:
      cluster_operations.Await(
          op_ref, 'Exporting cluster', self.ReleaseTrack(), False
      )
    log.status.Print('Operation ID: {}'.format(op_ref.Name()))
    return op
