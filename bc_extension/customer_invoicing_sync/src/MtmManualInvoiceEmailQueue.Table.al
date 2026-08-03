table 71015 "MTM Manual Inv Email Queue"
{
    Caption = 'MTM Manual Invoice Email Queue';
    DataClassification = CustomerContent;

    fields
    {
        field(1; "Posted Invoice System Id"; Guid)
        {
            Caption = 'Posted Invoice System Id';
            DataClassification = SystemMetadata;
        }
        field(2; "Posted Invoice No."; Code[20])
        {
            Caption = 'Posted Invoice No.';
            DataClassification = CustomerContent;
        }
        field(3; "Customer No."; Code[20])
        {
            Caption = 'Customer No.';
            DataClassification = CustomerContent;
        }
        field(4; "External Document No."; Code[35])
        {
            Caption = 'External Document No.';
            DataClassification = CustomerContent;
        }
        field(5; Status; Option)
        {
            Caption = 'Status';
            DataClassification = SystemMetadata;
            OptionMembers = WaitingForStamp,ReadyToSend,Sending,Sent,ReviewRequired,Cancelled;
            OptionCaption = 'Waiting for FEL Stamp,Ready to Send,Sending,Sent,Review Required,Cancelled';
        }
        field(6; "Enqueued At"; DateTime)
        {
            Caption = 'Enqueued At';
            DataClassification = SystemMetadata;
        }
        field(7; "Next Attempt At"; DateTime)
        {
            Caption = 'Next Attempt At';
            DataClassification = SystemMetadata;
        }
        field(8; "Stamp Wait Deadline"; DateTime)
        {
            Caption = 'Stamp Wait Deadline';
            DataClassification = SystemMetadata;
        }
        field(9; "Stamp Check Count"; Integer)
        {
            Caption = 'Stamp Check Count';
            DataClassification = SystemMetadata;
        }
        field(10; "Send Attempt Count"; Integer)
        {
            Caption = 'Send Attempt Count';
            DataClassification = SystemMetadata;
        }
        field(11; "Last Attempt At"; DateTime)
        {
            Caption = 'Last Attempt At';
            DataClassification = SystemMetadata;
        }
        field(12; "Last Error Text"; Text[2048])
        {
            Caption = 'Last Error Text';
            DataClassification = CustomerContent;
        }
        field(13; "Sent At"; DateTime)
        {
            Caption = 'Sent At';
            DataClassification = SystemMetadata;
        }
        field(14; "Captured By"; Text[100])
        {
            Caption = 'Captured By';
            DataClassification = EndUserIdentifiableInformation;
        }
    }

    keys
    {
        key(PK; "Posted Invoice System Id") { Clustered = true; }
        key(StatusDue; Status, "Next Attempt At") { }
        key(InvoiceNo; "Posted Invoice No.") { }
    }
}
