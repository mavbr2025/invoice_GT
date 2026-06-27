page 71009 "MTM MX Sales Inv Draft API"
{
    PageType = API;
    APIPublisher = 'mtmlogix';
    APIGroup = 'invoiceSync';
    APIVersion = 'v1.0';
    EntityName = 'mxSalesInvoiceDraft';
    EntitySetName = 'mxSalesInvoiceDrafts';
    SourceTable = "Sales Header";
    SourceTableView = where("Document Type" = const(Invoice));
    ODataKeyFields = SystemId;
    DelayedInsert = false;
    Extensible = false;
    InsertAllowed = false;
    ModifyAllowed = true;
    DeleteAllowed = false;
    Permissions =
        tabledata "Sales Header" = rm;

    layout
    {
        area(Content)
        {
            repeater(General)
            {
                field(id; Rec.SystemId)
                {
                    Caption = 'Id';
                    Editable = false;
                }
                field(number; Rec."No.")
                {
                    Caption = 'Number';
                    Editable = false;
                }
                field(customerNumber; Rec."Sell-to Customer No.")
                {
                    Caption = 'Customer Number';
                    Editable = false;
                }
                field(externalDocumentNumber; Rec."External Document No.")
                {
                    Caption = 'External Document Number';
                }
                field(paymentTermsCode; Rec."Payment Terms Code")
                {
                    Caption = 'Payment Terms Code';
                }
                field(paymentMethodCode; Rec."Payment Method Code")
                {
                    Caption = 'Payment Method Code';
                }
                field(dueDate; Rec."Due Date")
                {
                    Caption = 'Due Date';
                }
                field(currencyCode; Rec."Currency Code")
                {
                    Caption = 'Currency Code';
                    Editable = false;
                }
                field(systemModifiedAt; Rec.SystemModifiedAt)
                {
                    Caption = 'System Modified At';
                    Editable = false;
                }
            }
        }
    }

    [ServiceEnabled]
    procedure SetMxPaymentFields(paymentTermsCode: Text; paymentMethodCode: Text; var ActionContext: WebServiceActionContext)
    var
        PaymentMethod: Record "Payment Method";
        PaymentTerms: Record "Payment Terms";
    begin
        if paymentTermsCode = '' then
            Error('Payment terms code is required.');
        if paymentMethodCode = '' then
            Error('Payment method code is required.');

        PaymentTerms.Get(CopyStr(paymentTermsCode, 1, MaxStrLen(PaymentTerms.Code)));
        PaymentMethod.Get(CopyStr(paymentMethodCode, 1, MaxStrLen(PaymentMethod.Code)));

        Rec.Validate("Payment Terms Code", PaymentTerms.Code);
        Rec.Validate("Payment Method Code", PaymentMethod.Code);
        Rec.Modify(true);

        ActionContext.SetObjectType(ObjectType::Page);
        ActionContext.SetObjectId(Page::"MTM MX Sales Inv Draft API");
        ActionContext.AddEntityKey(Rec.FieldNo(SystemId), Rec.SystemId);
        ActionContext.SetResultCode(WebServiceActionResultCode::Updated);
    end;
}
