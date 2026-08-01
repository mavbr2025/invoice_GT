page 71012 "MTM Invoice Email Audit API"
{
    PageType = API;
    APIPublisher = 'mtmlogix';
    APIGroup = 'invoiceSync';
    APIVersion = 'v1.0';
    EntityName = 'invoiceEmailDelivery';
    EntitySetName = 'invoiceEmailDeliveries';
    SourceTable = "MTM Invoice Email Audit";
    ODataKeyFields = "Posted Invoice System Id";
    DelayedInsert = false;
    Extensible = false;
    InsertAllowed = false;
    ModifyAllowed = false;
    DeleteAllowed = false;

    layout
    {
        area(Content)
        {
            repeater(General)
            {
                field(postedInvoiceId; Rec."Posted Invoice System Id") { Caption = 'Posted Invoice Id'; }
                field(postedInvoiceNumber; Rec."Posted Invoice No.") { Caption = 'Posted Invoice Number'; }
                field(customerNumber; Rec."Customer No.") { Caption = 'Customer Number'; }
                field(recipient; Rec.Recipient) { Caption = 'Recipient'; }
                field(senderEmail; Rec."Sender Email") { Caption = 'Sender Email'; }
                field(status; StatusTxt) { Caption = 'Status'; }
                field(sentAt; Rec."Sent At") { Caption = 'Sent At'; }
                field(errorText; Rec."Error Text") { Caption = 'Error Text'; }
                field(attemptCount; Rec."Attempt Count") { Caption = 'Attempt Count'; }
                field(reportLayoutName; Rec."Report Layout Name") { Caption = 'Report Layout Name'; }
                field(bcEmailMessageId; Rec."BC Email Message Id") { Caption = 'BC Email Message Id'; }
                field(senderAccountId; Rec."Sender Account Id") { Caption = 'Sender Account Id'; }
                field(nativeSendAccepted; Rec."Native Send Accepted") { Caption = 'Native Send Accepted'; }
                field(nativeSentVerified; Rec."Native Sent Verified") { Caption = 'Native Sent Verified'; }
                field(lastAttemptAt; Rec."Last Attempt At") { Caption = 'Last Attempt At'; }
            }
        }
    }

    trigger OnAfterGetRecord()
    begin
        StatusTxt := Format(Rec.Status);
    end;

    var
        StatusTxt: Text[30];
}
