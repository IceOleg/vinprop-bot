# -*- coding: utf-8 -*- #
# Copyright 2023 Google LLC. All Rights Reserved.
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
"""Implements the command to upload Generic artifacts to a repository."""

from __future__ import absolute_import
from __future__ import division
from __future__ import unicode_literals

from apitools.base.py import exceptions as apitools_exceptions
from apitools.base.py import list_pager
from googlecloudsdk.api_lib.artifacts import exceptions as ar_exceptions
from googlecloudsdk.api_lib.util import apis
from googlecloudsdk.calliope import base
from googlecloudsdk.command_lib.artifacts import docker_util
from googlecloudsdk.command_lib.artifacts import endpoint_util
from googlecloudsdk.command_lib.artifacts import flags
from googlecloudsdk.command_lib.artifacts import requests as ar_requests
from googlecloudsdk.command_lib.artifacts import vex_util
from googlecloudsdk.core import properties


@base.DefaultUniverseOnly
@base.ReleaseTracks(base.ReleaseTrack.GA)
class LoadVex(base.Command):
  """Load VEX data from a CSAF file into Artifact Analysis.

  Command loads VEX data from a Common Security Advisory Framework (CSAF) file
  into Artifact Analysis as VulnerabilityAssessment Notes. VEX data tells
  Artifact Analysis whether vulnerabilities are relevant and how.
  """

  detailed_help = {
      'DESCRIPTION': '{description}',
      'EXAMPLES': """\
       To load a CSAF security advisory file given an artifact in Artifact Registry and the file on disk, run:

        $ {command} --uri=us-east1-docker.pkg.dev/project123/repository123/someimage@sha256:49765698074d6d7baa82f --source=/path/to/vex/file

To load a CSAF security advisory file given an artifact with a tag and a file on disk, run:

        $ {command} --uri=us-east1-docker.pkg.dev/project123/repository123/someimage:latest --source=/path/to/vex/file
    """,
  }
  ca_client = None
  ca_messages = None

  @staticmethod
  def Args(parser):
    parser.add_argument(
        '--uri',
        required=True,
        help=(
            "The path of the artifact in Artifact Registry. A 'gcr.io' image"
            ' can also be used if redirection is enabled in Artifact Registry.'
            " Make sure 'artifactregistry.projectsettings.get' permission is"
            ' granted to the current gcloud user to verify the redirection'
            ' status.'
        ),
    )
    parser.add_argument(
        '--source',
        required=True,
        help='The path of the VEX file.',
    )
    parser.add_argument(
        '--project',
        required=False,
        help='The parent project to load security advisory into.',
    )
    flags.GetOptionalAALocationFlag().AddToParser(parser)
    return

  def Run(self, args):
    """Run the generic artifact upload command."""
    with endpoint_util.WithRegion(args.location):
      self.ca_client = apis.GetClientInstance('containeranalysis', 'v1')
      self.ca_messages = self.ca_client.MESSAGES_MODULE
    uri = args.uri
    uri = vex_util.RemoveHTTPS(uri)
    if docker_util.IsARDockerImage(uri):
      image, version = docker_util.DockerUrlToImage(uri)
      image_uri = image.GetDockerString()
      version_uri = version.GetDockerString() if version else None
      image_project = image.project
    elif docker_util.IsGCRImage(uri):
      image_project, image_uri, version_uri = vex_util.ParseGCRUrl(uri)
      messages = ar_requests.GetMessages()
      settings = ar_requests.GetProjectSettings(image_project)
      if (
          settings.legacyRedirectionState
          != messages.ProjectSettings.LegacyRedirectionStateValueValuesEnum.REDIRECTION_FROM_GCR_IO_ENABLED
      ):
        raise ar_exceptions.InvalidInputValueError(
            'This command only supports Artifact Registry. You can enable'
            ' redirection to use gcr.io repositories in Artifact Registry.'
        )
    else:
      raise ar_exceptions.InvalidInputValueError(
          '{} is not an Artifact Registry image.'.format(uri)
      )

    project = args.project or image_project
    filename = args.source
    notes, generic_uri = vex_util.ParseVexFile(filename, image_uri, version_uri)
    self.writeNotes(notes, project, generic_uri, args.location)
    return

  def writeNotes(self, notes, project, uri, location):
    notes_to_create = []
    notes_to_update = []
    parent = self.parent(project, location)
    for note in notes:
      get_request = self.ca_messages.ContaineranalysisProjectsNotesGetRequest(
          name='{}/notes/{}'.format(parent, note.key)
      )
      try:
        self.ca_client.projects_notes.Get(get_request)
        note_exists = True
      except apitools_exceptions.HttpNotFoundError:
        note_exists = False
      if note_exists:
        notes_to_update.append(note)
      else:
        notes_to_create.append(note)
    self.batchWriteNotes(notes_to_create, project, location)
    self.updateNotes(notes_to_update, project, location)

    # Delete notes that are not in the uploaded file (deleteNotes looks at which
    # notes are stored in the db but not in the uploaded file and deletes
    # those).
    self.deleteNotes(notes, project, uri, location)

  def batchWriteNotes(self, notes, project, location):
    # Helper function to validate the artifacts/max_notes_per_batch_request
    # hidden flag. The value must be an integer between 1 and 1000.
    def validate_max_notes_per_batch_request(note_limit_str):
      try:
        max_notes_per_batch_request = int(note_limit_str)
      except ValueError:
        raise ar_exceptions.InvalidInputValueError(
            'max_notes_per_batch_request must be an integer'
        )
      if max_notes_per_batch_request < 1 or max_notes_per_batch_request > 1000:
        raise ar_exceptions.InvalidInputValueError(
            'max_notes_per_batch_request must be between 1 and 1000'
        )
      return max_notes_per_batch_request

    # Helper function to chunk notes into lists of max_notes_per_request size.
    def chunked(notes):
      notes_chunk = []
      for note in notes:
        notes_chunk.append(note)
        if len(notes_chunk) == max_notes_per_batch_request:
          yield notes_chunk
          notes_chunk = []

      # If there are any notes left over, yield them.
      if notes_chunk:
        yield notes_chunk

    # Default batch size is 1000, based on the Container Analysis API
    # BatchWriteNotes request. Sometimes the default batch size is reduced for
    # testing.
    max_notes_per_batch_request = validate_max_notes_per_batch_request(
        properties.VALUES.artifacts.max_notes_per_batch_request.Get()
    )

    # Split notes into chunks to avoid exceeding the max notes per batch
    # request limit.
    for notes_chunk in chunked(notes):
      if not notes_chunk:
        return
      note_value = self.ca_messages.BatchCreateNotesRequest.NotesValue()
      note_value.additionalProperties = notes_chunk
      batch_request = self.ca_messages.BatchCreateNotesRequest(
          notes=note_value,
      )
      request = (
          self.ca_messages.ContaineranalysisProjectsNotesBatchCreateRequest(
              parent=self.parent(project, location),
              batchCreateNotesRequest=batch_request,
          )
      )
      self.ca_client.projects_notes.BatchCreate(request)

  def updateNotes(self, notes, project, location):
    if not notes:
      return
    parent = self.parent(project, location)
    for note in notes:
      patch_request = (
          self.ca_messages.ContaineranalysisProjectsNotesPatchRequest(
              name='{}/notes/{}'.format(parent, note.key),
              note=note.value,
          )
      )
      self.ca_client.projects_notes.Patch(patch_request)

  def deleteNotes(self, file_notes, project, uri, location):
    list_request = self.ca_messages.ContaineranalysisProjectsNotesListRequest(
        filter='vulnerability_assessment.product.generic_uri="{}"'.format(uri),
        parent=self.parent(project, location),
    )
    db_notes = list_pager.YieldFromList(
        service=self.ca_client.projects_notes,
        request=list_request,
        field='notes',
        batch_size_attribute='pageSize',
    )

    cves_in_file = set()
    for file_note in file_notes:
      file_uri = file_note.value.vulnerabilityAssessment.product.genericUri
      file_vulnerability = (
          file_note.value.vulnerabilityAssessment.assessment.vulnerabilityId
      )
      if file_uri == uri:
        cves_in_file.add(file_vulnerability)

    for db_note in db_notes:
      db_vulnerability = (
          db_note.vulnerabilityAssessment.assessment.vulnerabilityId
      )
      if db_vulnerability not in cves_in_file:
        delete_request = (
            self.ca_messages.ContaineranalysisProjectsNotesDeleteRequest(
                name=db_note.name
            )
        )
        self.ca_client.projects_notes.Delete(delete_request)

  def parent(self, project, location):
    if location is not None:
      return 'projects/{}/locations/{}'.format(project, location)
    return 'projects/{}'.format(project)
