# -*- coding: utf-8 -*-
#
# This file is part of Invenio.
# Copyright (C) 2016 CERN.
#
# Invenio is free software; you can redistribute it
# and/or modify it under the terms of the GNU General Public License as
# published by the Free Software Foundation; either version 2 of the
# License, or (at your option) any later version.
#
# Invenio is distributed in the hope that it will be
# useful, but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Invenio; if not, write to the
# Free Software Foundation, Inc., 59 Temple Place, Suite 330, Boston,
# MA 02111-1307, USA.
#
# In applying this license, CERN does not
# waive the privileges and immunities granted to it by virtue of its status
# as an Intergovernmental Organization or submit itself to any jurisdiction.

"""File reader utility."""

from __future__ import absolute_import, print_function

import errno
import os
import re
import shutil
import subprocess
from os.path import basename, splitext
from time import sleep

from flask import current_app, flash, redirect, request, url_for
from flask_babelex import gettext as _


class PreviewFile(object):
    """Preview file default implementation."""

    def __init__(self, pid, record, fileobj, allow_aggs=True):
        """Default constructor.

        :param file: ObjectVersion instance from Invenio-Files-REST.
        """
        self.file = fileobj
        self.pid = pid
        self.record = record
        self.allow_aggs = allow_aggs

    @property
    def size(self):
        """Get file size."""
        return self.file['size']

    @property
    def filename(self):
        """Get filename."""
        return basename(self.file.key)

    @property
    def bucket(self):
        """Get bucket."""
        return self.file.bucket_id

    @property
    def uri(self):
        """Get file download link.

        ..  note::

            The URI generation assumes that you can download the file using the
            view ``invenio_records_ui.<pid_type>_files``.
        """
        return url_for(
            '.{0}_file_preview'.format(self.pid.pid_type),
            pid_value=self.pid.pid_value,
            filename=self.file.key,
            allow_aggs=self.allow_aggs)

    def is_local(self):
        """Check if file is local."""
        return True

    def has_extensions(self, *exts):
        """Check if file has one of the extensions."""
        file_ext = splitext(self.filename)[1]
        file_ext = file_ext.lower()

        for e in exts:
            if file_ext == e:
                return True
        return False

    def open(self):
        """Open the file."""
        return self.file.file.storage().open()


def convert_to(folder, source):
    """Convert file to pdf."""
    def redirect_detail_page(pid_value):
        return redirect(
            current_app.config[
                'RECORDS_UI_ENDPOINTS']['recid']['route'].replace(
                    '<pid_value>', pid_value
            )
        )

    timeout = current_app.config['PREVIEWER_CONVERT_PDF_TIMEOUT']
    args = [
        'libreoffice',
        '--headless',
        '--convert-to',
        'pdf',
        '--outdir',
        folder,
        source
    ]
    os_env = dict(os.environ)
    temp_folder = "/tmp/" + source.split("/")[-2] + "_libreoffice"

    if os.path.exists(temp_folder):
        shutil.rmtree(temp_folder)

    os.mkdir(temp_folder)
    # Change home var for next subprocess for process runs faster.
    os_env['HOME'] = temp_folder
    filename = err_txt = None
    pid_value = request.path.split('/').pop(2)

    try:
        process_count = 0

        while (
            not filename and process_count
            <= current_app.config.get('PREVIEWER_CONVERT_PDF_RETRY_COUNT')
        ):
            process = subprocess.run(
                args,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=os_env,
                timeout=timeout
            )
            filename = re.search(
                '-> (.*?) using filter',
                process.stdout.decode()
            )

            if not filename:
                current_app.logger.debug(
                    'retry convert to pdf :' + str(process_count)
                )
                sleep(1)

            process_count = process_count + 1
    except FileNotFoundError as ex:
        current_app.logger.error(ex)
        err_txt = ''.join((
            _('The storage path is incorrect.'),
            '{' + folder + '} ',
            _('Please contact the administrator.')
        ))
        flash(err_txt, category='error')
        redirect_detail_page(pid_value)
    except PermissionError as ex:
        current_app.logger.error(ex)
        err_txt = ''.join((
            _('The storage location cannot be accessed.'),
            '{' + folder + '} ',
            _('Please contact the administrator.')
        ))
        flash(err_txt, category='error')
        redirect_detail_page(pid_value)
    except OSError as ex:
        if ex.errno == errno.ENOSPC:
            current_app.logger.error(ex)
            err_txt = ''.join((
                _('There is not enough storage space.'),
                _('Please contact the administrator.')
            ))
        flash(err_txt, category='error')
        redirect_detail_page(pid_value)
    except Exception as ex:
        current_app.logger.error(ex)
        # Fill strings if necessary
        err_txt = ''
        flash(err_txt, category='error')
        redirect_detail_page(pid_value)
    finally:
        shutil.rmtree(temp_folder)

    if filename is None:
        current_app.logger.error('convert to pdf failure')
        raise LibreOfficeError(process.stdout.decode())
    else:
        return filename.group(1)


class LibreOfficeError(Exception):
    """Libreoffice process error."""

    def __init__(self, output):
        """Init."""
        self.output = output
