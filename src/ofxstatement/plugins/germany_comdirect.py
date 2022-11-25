import csv
from decimal import Decimal
from hashlib import sha256

from ofxstatement.plugin import Plugin
from ofxstatement.parser import StatementParser
from ofxstatement.statement import (
    Statement,
    StatementLine,
    generate_transaction_id,
    )


class ComdirectPlugin(Plugin):
    """
    Plugin for German bank Comdirect
    """

    def get_parser(self, filename):
        return ComdirectParser(
            filename,
            self.settings.get('encoding', 'cp1252'),
            self.settings.get('account', ''),
            )


def _truncate_str(s):
    s = s.strip()
    s = ' '.join(s.split())
    return s[:46] + '...' if len(s) > 49 else s


class ComdirectParser(StatementParser):
    """
    TODO: Parses CSV files as downloaded from the Sparkasse's homepage. Following
    columns are expected:

        "Auftragskonto"
        "Buchungstag"
        "Valutadatum"
        "Buchungstext"
        "Verwendungszweck"
        "Glaeubiger ID"
        "Mandatsreferenz"
        "Kundenreferenz (End-to-End)"
        "Sammlerreferenz"
        "Lastschrift Ursprungsbetrag"
        "Auslagenersatz Ruecklastschrift"
        "Beguenstigter/Zahlungspflichtiger"
        "Kontonummer/IBAN"
        "BIC (SWIFT-Code)"
        "Betrag"
        "Waehrung"
        "Info"
    """

    date_format = '%d.%m.%Y'
    statement = None

    def __init__(self, file_name, file_encoding, account_id):
        self.statement = Statement(
            currency='EUR',
            bank_id='FRSPDE66XXX',  # FIXME: BIC Sparkasse Freiburg
            account_id=account_id,
            )
        self.file_name = file_name
        self.file_encoding = file_encoding

    def split_records(self):
        """
        Return a generator that yields csv lines (dicts)
        """
        f = open(
            self.file_name,
            mode='rt',
            encoding=self.file_encoding,
            newline='',  # As recommended in doc of csv module
            )
        try:
            reader = csv.DictReader(f, delimiter=';')
            yield from reader
        finally:
            f.close()

    def parse_record(self, line):
        """
        Parse given transaction line and return StatementLine object

        """
        sl = StatementLine()
        print(line)
        if (line['Buchungstag'] == "offen"):
            return None
        sl.amount = Decimal(line['Umsatz in EUR']
                            .replace('.', '')
                            .replace(',', '.'))
        # TODO trntype could be improved using 'Buchungstext'
        if sl.amount.is_signed():
            sl.trntype = 'DEBIT'
        else:
            sl.trntype = 'CREDIT'
        # .date: It is debatable whether to use 'Buchungstag' or 'Valutadatum'
        sl.date = self.parse_datetime(line['Wertstellung (Valuta)'])
        # .date_user is not contained in the original CSV

        # .payee becomes OFX.NAME which becomes "Description" in gnuCash
        # .memo  becomes OFX.MEMO which becomes "Notes"       in gnuCash
        # When .payee is empty, GnuCash imports .memo to "Description" and
        # keeps "Notes" empty
        #
        # OFX's <NAME> and <PAYEE> are distinct fields. But ofxstatement's
        # .payee is translated to OFX's <NAME>
        #
        # According to the OFX spec (version 2.1.1):
        #     <NAME>      Name of payee or description of transaction, A-32
        #                 Note: Provide NAME or PAYEE, not both
        #     <MEMO>      Extra information (not in <NAME>)
        #
        # I prefer to have a description in .payee because that's what it ends
        # up being in gnuCash.

        recipient = _truncate_str(line['Buchungstext'])
        if not recipient:
            recipient = 'UNBEKANNT'
        sl.payee = recipient
        sl.memo = recipient

        m = sha256()
        m.update(str(sl.date).encode('utf-8'))
        m.update(sl.payee.encode('utf-8'))
        m.update(sl.memo.encode('utf-8'))
        m.update(str(sl.amount).encode('utf-8'))

        # Shorten the hash to the first 16 digits just to make it more
        # manageable. It should still be enough.
        sl.id = str(abs(int(m.hexdigest(), 16)))[:16]

        return sl
