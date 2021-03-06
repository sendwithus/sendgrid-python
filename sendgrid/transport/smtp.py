import smtplib
import mimetypes
from email import utils
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders, charset
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email.header import Header
from email import base64mime

from sendgrid import exceptions

# Overwrite how utf-8 bodies are handled, instead of base64encoding use
# quote-printable
charset.add_charset('utf-8', charset.QP, charset.QP, 'utf-8')


class Smtp(object):
    """
    Transport to send emails using smtp
    """
    HOSTPORT = ('smtp.sendgrid.net', 587)

    def __init__(self, username, password, **opts):
        """
        Construct smtp transport object

        Args:
            username: Sendgrid uaername
            password: Sendgrid password
            tls: Use TLS
        """
        self.username = username
        self.password = password
        self.tls = opts.get('tls', True)

    def send(self, message):
        """
        Send message

        Args:
            message: Sendgrid Message object

        Returns:
            True on success

        Raises:
            SGServiceException: on error
        """

        # Compose the message.  If there are two bodies we need to create two
        # mime entities, otherwise we send one message
        email_message = MIMEMultipart('related')

        if message.text and message.html:
            alt_message = MIMEMultipart('alternative')
            alt_message.attach(self._getMessageMIME(message.text, 'plain'))
            alt_message.attach(self._getMessageMIME(message.html, 'html'))

            email_message.attach(alt_message)

        else:
            if message.text:
                email_message.attach(self._getMessageMIME(message.text, 'plain'))
            if message.html:
                email_message.attach(self._getMessageMIME(message.html, 'html'))

        email_message['From'] = self._encodeEmail(message.from_name, message.from_address)
        if message.to_name:
            email_message['To'] = ', '.join([self._encodeEmail(message.to_name[i], message.to[i]) for i in range(0, len(message.to))])
        else:
            email_message['To'] = ', '.join(message.to)

        # Add Reply-To
        if message.reply_to:
            email_message['Reply-To'] = message.reply_to

        # Add CC recipients to message header
        if message.cc:
            email_message['Cc'] = ', '.join(message.cc)

        # Add subject
        email_message['Subject'] = self._encodeHeader(message.subject)
        # Add date
        email_message['Date'] = message.date
        # Add JSON header
        if message.header.data:
            email_message['X-SMTPAPI'] = Header(message.header.as_json(), charset='8bit', maxlinelen=20480000)

        # Add custom headers
        headerError = False
        if message.headers:
            for k, v in message.headers.iteritems():
                if isinstance(k, basestring) and isinstance(v, basestring) and self._isAscii(k):
                    email_message[k] = self._encodeHeader(v)
                else:
                    headerError = True
                    break

            if headerError:
                raise ValueError('JSON in headers is valid but incompatible')

        # build a list of recipients (hide BCC recipients from header)
        recipients = email_message['To'].split(', ')
        if message.cc:
            recipients += message.cc
        if message.bcc:
            recipients += message.bcc

        # Add files if any
        if message.attachments:
            for attach in message.attachments:
                f = self._getFileMIME(attach)
                if f:
                    email_message.attach(f)

        server = smtplib.SMTP(*self.HOSTPORT)
        if self.tls:
            server.starttls()

        try:
            server.login(self.username, self.password)
            server.sendmail(email_message['From'],
                            recipients,
                            email_message.as_string())
            server.quit()
        except Exception, e:
            raise exceptions.SGServiceException(e)

        return True

    def _getMessageMIME(self, payload, subtype):
        """
        Create a text based MIME part from the given text
        """
        return MIMEText(payload.encode('utf-8'), subtype, 'utf-8')

    def _encodeEmail(self, name, e):
        encoded_name = str(Header(unicode(name), 'ISO-8859-1'))
        encoded_e = e.encode('ascii')
        return utils.formataddr((encoded_name, encoded_e))

    def _encodeHeader(self, header):
        """
        If header is non-ascii, encode it in utf-8
        """
        if not self._isAscii(header):
            try:
                h = Header(header, 'utf-8')
                return h
            except:
                pass
        return header

    def _isAscii(self, s):
        """
        Checks if the given string is in ascii format
        """
        try:
            s.encode('ascii')
        except UnicodeError:
            return False
        return True

    def _getFileMIME(self, attach):
        """
        Get a MIME part from the given file uploaded
        """
        filename = attach['name']
        try:
            f = open(attach['file'], 'rb')
            data = f.read()
            f.close()
        except:
            data = attach['file']

        ctype, encoding = mimetypes.guess_type(filename)
        if ctype is None or encoding is not None:
            ctype = 'application/octet-stream'
        maintype, subtype = ctype.split('/', 1)
        if maintype == 'text':
            msg = MIMEText(data, _subtype=subtype)
        elif maintype == 'image':
            msg = MIMEImage(data, _subtype=subtype)
        elif maintype == 'audio':
            msg = MIMEAudio(data, _subtype=subtype)
        else:
            msg = MIMEBase(maintype, subtype)
            msg.set_payload(data)
            encoders.encode_base64(msg)

        if attach.get('cid', False):
            msg.add_header('Content-ID', '<%s>' % attach['cid'])
        else:
            msg.add_header('Content-Disposition', 'attachment', filename=filename)

        return msg
