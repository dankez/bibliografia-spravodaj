import assert from 'node:assert/strict';
import test from 'node:test';

import {
  buildErrataNotificationEmail,
  errataEmailConfig,
  sendSmtpEmail,
} from '../web/functions/_lib/email-notifications.js';

test('errataEmailConfig requires SMTP password before enabling notifications', () => {
  assert.equal(errataEmailConfig({ ERRATA_EMAIL_TO: 'bibliografia@sss.sk' }), null);

  const config = errataEmailConfig({
    ERRATA_EMAIL_TO: 'bibliografia@sss.sk, admin@example.com',
    ERRATA_EMAIL_FROM: 'Digitalna bibliografia SSS <admin@sss.sk>',
    ERRATA_EMAIL_REPLY_TO: 'bibliografia@sss.sk',
    ERRATA_SMTP_HOST: 'smtp.m1.websupport.sk',
    ERRATA_SMTP_PORT: '465',
    ERRATA_SMTP_USERNAME: 'admin@sss.sk',
    ERRATA_SMTP_PASSWORD: 'secret',
  });

  assert.deepEqual(config.recipients, ['bibliografia@sss.sk', 'admin@example.com']);
  assert.equal(config.smtp.host, 'smtp.m1.websupport.sk');
  assert.equal(config.smtp.port, 465);
  assert.equal(config.from, 'Digitalna bibliografia SSS <admin@sss.sk>');
  assert.equal(config.replyTo, 'bibliografia@sss.sk');
});

test('buildErrataNotificationEmail includes escaped issue, admin and article details', () => {
  const email = buildErrataNotificationEmail({
    issueUrl: 'https://github.com/dankez/bibliografia-spravodaj/issues/12',
    adminUrl: 'https://bibliografia.sss.sk/admin/opravy/',
    data: {
      type: 'article_edit',
      articleId: '4133',
      articleTitle: '<Zahraničné aktivity & test>',
      articleUrl: '/clanky/4133/',
      changedFields: ['title', 'abstract'],
      sourceVersion: 'v1.0.0-beta.20260630+abc123',
      email: 'reader@example.com',
      message: 'Treba opraviť <script>alert(1)</script> a diakritiku.',
    },
  });

  assert.match(email.subject, /#4133/);
  assert.match(email.text, /https:\/\/github.com\/dankez\/bibliografia-spravodaj\/issues\/12/);
  assert.match(email.text, /https:\/\/bibliografia\.sss\.sk\/admin\/opravy\/\?issue=12/);
  assert.match(email.html, /&lt;Zahraničné aktivity &amp; test&gt;/);
  assert.match(email.html, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
  assert.doesNotMatch(email.html, /<script>alert/);
  assert.match(email.html, /title, abstract/);
  assert.match(email.html, /https:\/\/bibliografia\.sss\.sk\/admin\/opravy\/\?issue=12/);
});

test('sendSmtpEmail authenticates and sends one HTML message over a secure socket', async () => {
  const writes = [];
  let connectAddress = null;
  let connectOptions = null;
  const responses = [
    '220 smtp.example ESMTP ready',
    '250-smtp.example',
    '250 AUTH LOGIN PLAIN',
    '334 VXNlcm5hbWU6',
    '334 UGFzc3dvcmQ6',
    '235 2.7.0 Authentication successful',
    '250 2.1.0 Sender OK',
    '250 2.1.5 Recipient OK',
    '354 End data with <CR><LF>.<CR><LF>',
    '250 2.0.0 Message queued',
    '221 2.0.0 Bye',
  ].join('\r\n') + '\r\n';

  const socket = {
    readable: new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(responses));
      },
    }),
    writable: new WritableStream({
      write(chunk) {
        writes.push(new TextDecoder().decode(chunk));
      },
    }),
    opened: Promise.resolve({}),
    close: async () => {},
  };

  const connect = (address, options) => {
    connectAddress = address;
    connectOptions = options;
    return socket;
  };

  await sendSmtpEmail(
    {
      smtp: {
        host: 'smtp.m1.websupport.sk',
        port: 465,
        username: 'admin@sss.sk',
        password: 'secret',
        secureTransport: 'on',
      },
      from: 'Digitalna bibliografia SSS <admin@sss.sk>',
      recipients: ['bibliografia@sss.sk'],
      replyTo: 'bibliografia@sss.sk',
    },
    {
      subject: 'Nová oprava: článok #4133',
      text: 'Line 1\n.Line starting with a dot',
      html: '<p>Line 1</p>',
    },
    { connect }
  );

  const transcript = writes.join('');
  assert.deepEqual(connectAddress, { hostname: 'smtp.m1.websupport.sk', port: 465 });
  assert.deepEqual(connectOptions, { secureTransport: 'on' });
  assert.match(transcript, /EHLO bibliografia\.sss\.sk\r\n/);
  assert.match(transcript, /AUTH LOGIN\r\n/);
  assert.match(transcript, new RegExp(`${Buffer.from('admin@sss.sk').toString('base64')}\\r\\n`));
  assert.match(transcript, new RegExp(`${Buffer.from('secret').toString('base64')}\\r\\n`));
  assert.match(transcript, /MAIL FROM:<admin@sss\.sk>\r\n/);
  assert.match(transcript, /RCPT TO:<bibliografia@sss\.sk>\r\n/);
  assert.match(transcript, /Subject: =\?UTF-8\?B\?/);
  assert.match(transcript, /Content-Type: text\/html; charset=UTF-8/);
  assert.match(transcript, /\r\n\.\.Line starting with a dot\r\n/);
  assert.match(transcript, /\r\n\.\r\nQUIT\r\n/);
});
